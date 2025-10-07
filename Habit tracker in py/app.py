from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import pytz
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

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


class Entry(db.Model):
    __tablename__ = 'entries'
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habits.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    __table_args__ = (db.UniqueConstraint('habit_id', 'date', name='_habit_date_uc'),)


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


# ---- DB Bootstrap (robust für Render/Gunicorn) ----
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

    entries = {}
    for habit in habits:
        entry = Entry.query.filter_by(habit_id=habit.id, date=today).first()
        entries[habit.id] = entry.completed if entry else False

    completed_today = sum(1 for v in entries.values() if v)
    today_rate = round((completed_today / len(habits)) * 100, 1) if habits else 0

    return render_template('today.html', habits=habits, entries=entries, today=today, today_rate=today_rate)


@app.route('/month')
@app.route('/month/<int:year>/<int:month>/<int:offset>')
def month_view(year=None, month=None, offset=0):
    today = datetime.now(TIMEZONE).date()
    u = current_user()
    max_back = 0

    start_date = today - timedelta(days=6) + timedelta(days=offset * 7)
    end_date = today + timedelta(days=offset * 7)

    if offset < max_back:
        return redirect(url_for('month_view', year=today.year, month=today.month, offset=max_back))

    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()
    stats = []
    calendar_data = {}

    for habit in habits:
        entries = Entry.query.filter(
            Entry.habit_id == habit.id,
            Entry.date >= start_date,
            Entry.date <= end_date
        ).all()
        calendar_data[habit.id] = {e.date.isoformat(): e.completed for e in entries}

        total_days = 7
        completed = sum(1 for e in entries if e.completed)
        rate = (completed / total_days * 100) if total_days > 0 else 0

        stats.append({
            'habit': habit,
            'rate': round(rate, 1),
            'current_streak': 0,
            'longest_streak': 0,
            'trend': 0
        })

    overall_rate = sum(s['rate'] for s in stats) / len(stats) if stats else 0

    return render_template(
        'month.html',
        stats={'habits': stats, 'overall_rate': overall_rate, 'start_date': start_date, 'end_date': end_date},
        calendar_data=calendar_data,
        year=year or today.year,
        month=month or today.month,
        today=today,
        offset=offset,
        max_back=max_back
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
    return jsonify([{ 'id': h.id, 'name': h.name, 'category': h.category, 'position': h.position, 'emoji': h.emoji } for h in habits])


@app.route('/api/habits', methods=['POST'])
def api_create_habit():
    u = current_user()
    data = request.get_json()
    max_pos = db.session.query(db.func.max(Habit.position)).filter(Habit.user_id == u.id).scalar() or -1
    habit = Habit(name=data['name'], category=data.get('category'), emoji=data.get('emoji'), position=max_pos + 1, user_id=u.id)
    db.session.add(habit)
    db.session.commit()
    return jsonify({'success': True, 'id': habit.id})


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
