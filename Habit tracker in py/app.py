from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, date, timedelta
import os
from dotenv import load_dotenv
import pytz
from sqlalchemy import text  # für Migration/PRAGMA

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///habits.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
csrf = CSRFProtect(app)

TIMEZONE = pytz.timezone('Europe/Berlin')

# =========================
# Models
# =========================
class Habit(db.Model):
    __tablename__ = 'habits'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TIMEZONE))
    emoji = db.Column(db.String(10))  # optionales Emoji
    entries = db.relationship('Entry', backref='habit', lazy=True, cascade='all, delete-orphan')

class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habits.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    __table_args__ = (db.UniqueConstraint('habit_id', 'date', name='_habit_date_uc'),)

# =========================
# Statistics Service
# =========================
class StatsService:
    @staticmethod
    def get_completion_rate(habit_id, start_date, end_date):
        total_days = (end_date - start_date).days + 1
        completed = Entry.query.filter(
            Entry.habit_id == habit_id,
            Entry.date >= start_date,
            Entry.date <= end_date,
            Entry.completed == True
        ).count()
        return (completed / total_days * 100) if total_days > 0 else 0

    @staticmethod
    def get_current_streak(habit_id, reference_date=None):
        if reference_date is None:
            reference_date = datetime.now(TIMEZONE).date()
        streak = 0
        current = reference_date
        while True:
            entry = Entry.query.filter_by(habit_id=habit_id, date=current).first()
            if entry and entry.completed:
                streak += 1
                current -= timedelta(days=1)
            else:
                break
        return streak

    @staticmethod
    def get_longest_streak(habit_id):
        entries = Entry.query.filter_by(
            habit_id=habit_id,
            completed=True
        ).order_by(Entry.date).all()

        if not entries:
            return 0

        max_streak = current_streak = 1
        for i in range(1, len(entries)):
            if (entries[i].date - entries[i-1].date).days == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 1
        return max_streak

    @staticmethod
    def get_month_stats(year, month):
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        habits = Habit.query.order_by(Habit.position).all()
        stats = []

        for habit in habits:
            rate = StatsService.get_completion_rate(habit.id, start_date, end_date)
            current_streak = StatsService.get_current_streak(habit.id, end_date)
            longest_streak = StatsService.get_longest_streak(habit.id)

            # Vergleich zum Vormonat
            if month == 1:
                prev_start = date(year - 1, 12, 1)
                prev_end = date(year - 1, 12, 31)
            else:
                prev_start = date(year, month - 1, 1)
                prev_end = start_date - timedelta(days=1)

            prev_rate = StatsService.get_completion_rate(habit.id, prev_start, prev_end)
            trend = rate - prev_rate

            stats.append({
                'habit': habit,
                'rate': round(rate, 1),
                'current_streak': current_streak,
                'longest_streak': longest_streak,
                'trend': round(trend, 1)
            })

        overall_rate = sum(s['rate'] for s in stats) / len(stats) if stats else 0
        return {
            'habits': stats,
            'overall_rate': round(overall_rate, 1),
            'start_date': start_date,
            'end_date': end_date
        }

# =========================
# Migration Helpers (SQLite)
# =========================
def column_exists(table_name, column_name):
    with app.app_context():
        rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return any(r['name'] == column_name for r in rows)

def migrate_db():
    """Idempotente Migration für bestehende SQLite-DBs."""
    with app.app_context():
        # habits.emoji nachrüsten
        if not column_exists('habits', 'emoji'):
            db.session.execute(text("ALTER TABLE habits ADD COLUMN emoji VARCHAR(10)"))
            db.session.commit()
            print("✓ DB migrated: added 'emoji' column to habits")

# =========================
# Routes
# =========================
@app.route('/')
def index():
    # today = datetime.now(TIMEZONE).date()   # echtes heutiges Datum
    today = date(2025, 9, 28)  # <-- Fake-Datum zum Testen

    habits = Habit.query.order_by(Habit.position).all()



    entries = {}
    for habit in habits:
        entry = Entry.query.filter_by(habit_id=habit.id, date=today).first()
        entries[habit.id] = entry.completed if entry else False

    # Heutige Erfüllungsrate
    if habits:
        completed_today = sum(1 for v in entries.values() if v)
        today_rate = round((completed_today / len(habits)) * 100, 1)
    else:
        today_rate = 0

    return render_template(
        'today.html',
        habits=habits,
        entries=entries,
        today=today,
        today_rate=today_rate
    )

@app.route('/week')
@app.route('/week/<int:year>/<int:week>')
def week_view(year=None, week=None):
    today = datetime.now(TIMEZONE).date()
    if year is None:
        year = today.isocalendar()[0]  # aktuelles Jahr
    if week is None:
        week = today.isocalendar()[1]  # aktuelle KW

    # Wochenanfang (Montag) berechnen
    first_day = date.fromisocalendar(year, week, 1)
    last_day = first_day + timedelta(days=6)

    habits = Habit.query.order_by(Habit.position).all()
    stats = []
    calendar_data = {}

    for habit in habits:
        entries = Entry.query.filter(
            Entry.habit_id == habit.id,
            Entry.date >= first_day,
            Entry.date <= last_day
        ).all()

        calendar_data[habit.id] = {e.date.isoformat(): e.completed for e in entries}

        total_days = 7
        completed = sum(1 for e in entries if e.completed)
        rate = (completed / total_days * 100) if total_days > 0 else 0

        stats.append({
            'habit': habit,
            'rate': round(rate, 1)
        })

    overall_rate = sum(s['rate'] for s in stats) / len(stats) if stats else 0

    return render_template(
        'week.html',
        stats=stats,
        calendar_data=calendar_data,
        year=year,
        week=week,
        overall_rate=round(overall_rate, 1),
        today=today,
        start_date=first_day,
        end_date=last_day
    )


@app.route('/settings')
def settings():
    habits = Habit.query.order_by(Habit.position).all()
    return render_template('settings.html', habits=habits)

# =========================
# API Routes
# =========================
@app.route('/api/toggle', methods=['POST'])
def api_toggle():
    data = request.get_json()
    habit_id = data.get('habit_id')
    date_str = data.get('date')

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format'}), 400

    entry = Entry.query.filter_by(habit_id=habit_id, date=target_date).first()

    if entry:
        entry.completed = not entry.completed
    else:
        entry = Entry(habit_id=habit_id, date=target_date, completed=True)
        db.session.add(entry)

    db.session.commit()

    return jsonify({
        'success': True,
        'completed': entry.completed
    })

@app.route('/api/habits', methods=['GET'])
def api_get_habits():
    habits = Habit.query.order_by(Habit.position).all()
    return jsonify([{
        'id': h.id,
        'name': h.name,
        'category': h.category,
        'position': h.position,
        'emoji': h.emoji
    } for h in habits])

@app.route('/api/habits', methods=['POST'])
def api_create_habit():
    data = request.get_json()
    max_position = db.session.query(db.func.max(Habit.position)).scalar() or -1

    habit = Habit(
        name=data['name'],
        category=data.get('category'),
        emoji=data.get('emoji'),
        position=max_position + 1
    )
    db.session.add(habit)
    db.session.commit()

    return jsonify({'success': True, 'id': habit.id})

@app.route('/api/habits/<int:habit_id>', methods=['PUT'])
def api_update_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    data = request.get_json()

    if 'name' in data:
        habit.name = data['name']
    if 'category' in data:
        habit.category = data['category']
    if 'position' in data:
        habit.position = data['position']
    if 'emoji' in data:
        habit.emoji = data['emoji']

    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/habits/<int:habit_id>', methods=['DELETE'])
def api_delete_habit(habit_id):
    habit = Habit.query.get_or_404(habit_id)
    db.session.delete(habit)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/stats/<int:year>/<int:month>')
def api_month_stats(year, month):
    stats = StatsService.get_month_stats(year, month)
    return jsonify({
        'overall_rate': stats['overall_rate'],
        'habits': [{
            'id': s['habit'].id,
            'name': s['habit'].name,
            'rate': s['rate'],
            'current_streak': s['current_streak'],
            'longest_streak': s['longest_streak'],
            'trend': s['trend']
        } for s in stats['habits']]
    })

# =========================
# DB Init + Defaults + Migration
# =========================
def init_db():
    with app.app_context():
        # Tabellen neu anlegen (falls DB frisch ist)
        db.create_all()
        # Bestehende DB updaten, bevor wir irgendetwas queryen
        migrate_db()

        # Default-Habits nur anlegen, wenn noch keine existieren
        if Habit.query.count() == 0:
            default_habits = [
                'Meditation',
                'Sport/Bewegung',
                'Gesund essen',
                'Wasser trinken',
                'Lesen',
                'Früh aufstehen'
            ]
            for i, name in enumerate(default_habits):
                db.session.add(Habit(name=name, position=i))
            db.session.commit()
            print("✓ Default habits created")

# =========================
# Main
# =========================
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)

