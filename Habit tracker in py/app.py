from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import pytz
from sqlalchemy import text, Index
from sqlalchemy.exc import OperationalError
from collections import defaultdict

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
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TIMEZONE))


class Habit(db.Model):
    __tablename__ = 'habits'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(TIMEZONE))
    emoji = db.Column(db.String(10))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref='habits')
    entries = db.relationship('Entry', backref='habit', lazy=True, cascade='all, delete-orphan')
    
    # Performance-Indizes
    __table_args__ = (
        Index('idx_user_position', 'user_id', 'position'),
    )


class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habits.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    __table_args__ = (
        db.UniqueConstraint('habit_id', 'date', name='_habit_date_uc'),
        Index('idx_habit_date', 'habit_id', 'date'),
    )


# =========================
# Statistics Service (NEU!)
# =========================
class StatsService:
    @staticmethod
    def get_completion_rate(habit_id, start_date, end_date):
        """Berechnet Completion Rate für Zeitraum"""
        entries = Entry.query.filter(
            Entry.habit_id == habit_id,
            Entry.date >= start_date,
            Entry.date <= end_date
        ).all()
        
        total_days = (end_date - start_date).days + 1
        completed = sum(1 for e in entries if e.completed)
        return (completed / total_days * 100) if total_days > 0 else 0
    
    @staticmethod
    def get_current_streak(habit_id, reference_date=None):
        """Berechnet aktuelle Streak (aufeinanderfolgende Tage)"""
        if reference_date is None:
            reference_date = datetime.now(TIMEZONE).date()
        
        entries = Entry.query.filter(
            Entry.habit_id == habit_id,
            Entry.date <= reference_date,
            Entry.completed == True
        ).order_by(Entry.date.desc()).all()
        
        if not entries:
            return 0
        
        streak = 0
        expected_date = reference_date
        
        for entry in entries:
            if entry.date == expected_date:
                streak += 1
                expected_date -= timedelta(days=1)
            elif entry.date < expected_date:
                break
        
        return streak
    
    @staticmethod
    def get_longest_streak(habit_id):
        """Findet längste jemals erreichte Streak"""
        entries = Entry.query.filter(
            Entry.habit_id == habit_id,
            Entry.completed == True
        ).order_by(Entry.date).all()
        
        if not entries:
            return 0
        
        max_streak = current_streak = 1
        last_date = entries[0].date
        
        for entry in entries[1:]:
            if (entry.date - last_date).days == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 1
            last_date = entry.date
        
        return max_streak
    
    @staticmethod
    def get_trend(habit_id, reference_date=None):
        """Berechnet Trend: Vergleich letzte 7 Tage vs. 7 Tage davor"""
        if reference_date is None:
            reference_date = datetime.now(TIMEZONE).date()
        
        recent_start = reference_date - timedelta(days=6)
        previous_start = reference_date - timedelta(days=13)
        previous_end = reference_date - timedelta(days=7)
        
        recent_rate = StatsService.get_completion_rate(habit_id, recent_start, reference_date)
        previous_rate = StatsService.get_completion_rate(habit_id, previous_start, previous_end)
        
        return recent_rate - previous_rate


# =========================
# DB / Migration Helpers
# =========================
def column_exists(table_name, column_name):
    with app.app_context():
        rows = db.session.execute(text(f"PRAGMA table_info({table_name})")).mappings().all()
        return any(r['name'] == column_name for r in rows)


def user_by_name(name):
    return User.query.filter_by(name=name).first()


def get_or_create_user(name):
    u = user_by_name(name)
    if not u:
        u = User(name=name)
        db.session.add(u)
        db.session.commit()
    return u


def migrate_db():
    with app.app_context():
        if not column_exists('habits', 'emoji'):
            db.session.execute(text("ALTER TABLE habits ADD COLUMN emoji VARCHAR(10)"))
            db.session.commit()
            print("✓ added emoji column")


def migrate_db_multitenant():
    with app.app_context():
        db.create_all()
        cols = db.session.execute(text("PRAGMA table_info(habits)")).mappings().all()
        colnames = {r['name'] for r in cols}
        if 'user_id' not in colnames:
            db.session.execute(text("ALTER TABLE habits ADD COLUMN user_id INTEGER"))
            db.session.commit()
            default_user = get_or_create_user('default')
            db.session.execute(text("UPDATE habits SET user_id = :uid WHERE user_id IS NULL"), {'uid': default_user.id})
            db.session.commit()
            print("✓ added user_id to habits")


_db_ready = False

def ensure_db_ready():
    global _db_ready
    if _db_ready:
        return
    with app.app_context():
        db.create_all()
        try:
            migrate_db()
        except Exception as e:
            app.logger.warning(f"migrate_db skipped/failed: {e}")
        try:
            migrate_db_multitenant()
        except Exception as e:
            app.logger.warning(f"migrate_db_multitenant skipped/failed: {e}")
        _db_ready = True

@app.before_request
def _bootstrap_before_each_request():
    ensure_db_ready()


# =========================
# User Context
# =========================
@app.before_request
def select_user_from_query():
    u = request.args.get('u')
    if u:
        session['user_name'] = u

def current_user():
    name = session.get('user_name', 'default')
    try:
        u = user_by_name(name)
    except OperationalError:
        ensure_db_ready()
        u = user_by_name(name)
    if not u:
        u = get_or_create_user(name)
    return u


# =========================
# Routes
# =========================
@app.route('/')
def index():
    today = datetime.now(TIMEZONE).date()
    u = current_user()
    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()

    # Optimiert: Eine Query statt N Queries
    entries_dict = {}
    if habits:
        habit_ids = [h.id for h in habits]
        entries = Entry.query.filter(
            Entry.habit_id.in_(habit_ids),
            Entry.date == today
        ).all()
        entries_dict = {e.habit_id: e.completed for e in entries}

    completed_today = sum(1 for v in entries_dict.values() if v)
    today_rate = round((completed_today / len(habits)) * 100, 1) if habits else 0

    return render_template('today.html', habits=habits, entries=entries_dict, today=today, today_rate=today_rate)


@app.route('/month')
@app.route('/month/<int:year>/<int:month>')
def month_view(year=None, month=None):
    today = datetime.now(TIMEZONE).date()
    u = current_user()
    
    # Standardwerte
    if year is None or month is None:
        year = today.year
        month = today.month
    
    # Ersten und letzten Tag des Monats berechnen
    start_date = datetime(year, month, 1, tzinfo=TIMEZONE).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1, tzinfo=TIMEZONE).date() - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1, tzinfo=TIMEZONE).date() - timedelta(days=1)

    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()
    
    # Alle Entries für den Monat in einer Query holen
    habit_ids = [h.id for h in habits]
    entries = Entry.query.filter(
        Entry.habit_id.in_(habit_ids),
        Entry.date >= start_date,
        Entry.date <= end_date
    ).all() if habit_ids else []
    
    # Entries gruppieren
    entries_by_habit = defaultdict(list)
    for entry in entries:
        entries_by_habit[entry.habit_id].append(entry)
    
    calendar_data = {}
    stats = []

    for habit in habits:
        habit_entries = entries_by_habit.get(habit.id, [])
        calendar_data[habit.id] = {e.date.isoformat(): e.completed for e in habit_entries}

        total_days = (end_date - start_date).days + 1
        completed = sum(1 for e in habit_entries if e.completed)
        rate = (completed / total_days * 100) if total_days > 0 else 0

        stats.append({
            'habit': habit,
            'rate': round(rate, 1),
            'current_streak': StatsService.get_current_streak(habit.id, end_date),
            'longest_streak': StatsService.get_longest_streak(habit.id),
            'trend': round(StatsService.get_trend(habit.id, end_date), 1)
        })

    overall_rate = sum(s['rate'] for s in stats) / len(stats) if stats else 0

    return render_template(
        'month.html',
        stats={'habits': stats, 'overall_rate': overall_rate, 'start_date': start_date, 'end_date': end_date},
        calendar_data=calendar_data,
        year=year,
        month=month,
        today=today
    )


@app.route('/settings')
def settings():
    u = current_user()
    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()
    return render_template('settings.html', habits=habits)


# =========================
# API
# =========================
@app.route('/api/habits', methods=['GET'])
def api_get_habits():
    u = current_user()
    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()
    return jsonify([{ 
        'id': h.id, 
        'name': h.name, 
        'category': h.category, 
        'position': h.position, 
        'emoji': h.emoji 
    } for h in habits])


@app.route('/api/habits', methods=['POST'])
def api_create_habit():
    u = current_user()
    data = request.get_json()
    max_pos = db.session.query(db.func.max(Habit.position)).filter(Habit.user_id == u.id).scalar() or -1
    habit = Habit(
        name=data['name'], 
        category=data.get('category'), 
        emoji=data.get('emoji'), 
        position=max_pos + 1, 
        user_id=u.id
    )
    db.session.add(habit)
    db.session.commit()
    return jsonify({'success': True, 'id': habit.id})


@app.route('/api/habits/<int:habit_id>', methods=['PUT'])
def api_update_habit(habit_id):
    """NEUE ROUTE: Habit aktualisieren"""
    u = current_user()
    habit = Habit.query.filter_by(id=habit_id, user_id=u.id).first()
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    
    data = request.get_json()
    if 'name' in data:
        habit.name = data['name']
    if 'category' in data:
        habit.category = data['category']
    if 'emoji' in data:
        habit.emoji = data['emoji']
    if 'position' in data:
        habit.position = data['position']
    
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/habits/<int:habit_id>', methods=['DELETE'])
def api_delete_habit(habit_id):
    u = current_user()
    habit = Habit.query.filter_by(id=habit_id, user_id=u.id).first()
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(habit)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/toggle', methods=['POST'])
def api_toggle():
    u = current_user()
    data = request.get_json()
    habit_id = data.get('habit_id')
    date_str = data.get('date')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    habit = Habit.query.filter_by(id=habit_id, user_id=u.id).first()
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    entry = Entry.query.filter_by(habit_id=habit.id, date=target_date).first()
    if entry:
        entry.completed = not entry.completed
    else:
        entry = Entry(habit_id=habit.id, date=target_date, completed=True)
        db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'completed': entry.completed})


if __name__ == '__main__':
    ensure_db_ready()
    app.run(debug=True, host='0.0.0.0', port=5000)
