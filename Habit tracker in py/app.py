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
import secrets
import json
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

load_dotenv()

# ----- App initialisieren -----
app = Flask(__name__)

# === Persistenz- & Secret-Setup ===
BASE_DIR = os.path.abspath(os.path.dirname(__file__))   # .../Habit-Tracker/Habit tracker in py/py
DATA_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data'))
os.makedirs(DATA_DIR, exist_ok=True)  # erstellt data/ beim App-Start auf dem Host

# Standard-Pfad zur SQLite-Datei (überschreibbar durch ENV DATABASE_URL)
default_db_path = f"sqlite:///{os.path.join(DATA_DIR, 'habits.db')}"
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', default_db_path)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SECRET_KEY: aus Environment, sonst ein dev-fallback (NICHT für Prod)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.environ.get('FLASK_SECRET_KEY', 'dev-secret-please-change'))

# Session-Einstellungen
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
# ================================

# Extensions initialisieren
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
TIMEZONE = pytz.timezone('Europe/Berlin')

# =========================
# File-based User Auth
# =========================
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

def load_users():
    try:
        if not os.path.exists(USERS_FILE):
            return {}
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        app.logger.warning(f"load_users failed: {e}")
        return {}

def save_users(users):
    try:
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        app.logger.error(f"save_users failed: {e}")

# Simple login_required decorator
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapped

# =========================
# Models
# =========================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    session_token = db.Column(db.String(64), unique=True, nullable=True)
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
# Statistics Service
# =========================
class StatsService:
    @staticmethod
    def get_completion_rate(habit_id, start_date, end_date):
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


def user_by_name(username):
    return User.query.filter_by(name=username).first()


def get_or_create_user_by_name(username):
    u = user_by_name(username)
    if not u:
        # Erstelle Benutzer falls nicht vorhanden
        u = User(name=username)
        db.session.add(u)
        db.session.commit()
    return u


def migrate_db():
    with app.app_context():
        if not column_exists('habits', 'emoji'):
            db.session.execute(text("ALTER TABLE habits ADD COLUMN emoji VARCHAR(10)"))
            db.session.commit()
            print("✓ added emoji column")
        
        if not column_exists('users', 'session_token'):
            db.session.execute(text("ALTER TABLE users ADD COLUMN session_token VARCHAR(64)"))
            db.session.commit()
            print("✓ added session_token column")


def migrate_db_multitenant():
    with app.app_context():
        db.create_all()
        cols = db.session.execute(text("PRAGMA table_info(habits)")).mappings().all()
        colnames = {r['name'] for r in cols}
        if 'user_id' not in colnames:
            db.session.execute(text("ALTER TABLE habits ADD COLUMN user_id INTEGER"))
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
def current_user():
    """Hole den aktuellen Benutzer basierend auf Session"""
    if 'user' not in session:
        return None
    
    username = session['user']['name']
    
    try:
        u = get_or_create_user_by_name(username)
    except OperationalError:
        ensure_db_ready()
        u = get_or_create_user_by_name(username)
    
    return u


# =========================
# Auth Routes
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registrierung neuer Benutzer"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            return render_template('register.html', error='Bitte Nutzername und Passwort angeben')
        
        users = load_users()
        if username in users:
            return render_template('register.html', error='Benutzer existiert bereits')
        
        users[username] = {'pw': generate_password_hash(password)}
        save_users(users)
        
        # nach Registrierung direkt zum Login weiterleiten
        return redirect(url_for('login'))
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login gegen data/users.json"""
    next_url = request.args.get('next') or url_for('index')
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        users = load_users()
        user = users.get(username)
        
        if user and check_password_hash(user.get('pw', ''), password):
            session['user'] = {'name': username}
            session.permanent = True
            return redirect(next_url)
        
        return render_template('login.html', error='Ungültige Zugangsdaten', next=next_url)
    
    return render_template('login.html', next=next_url)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


# =========================
# Routes (Protected)
# =========================
@app.route('/')
@login_required
def index():
    today = datetime.now(TIMEZONE).date()
    u = current_user()
    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()

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


@app.route('/week')
@app.route('/week/<int:year>/<int:week>')
@login_required
def week_view(year=None, week=None):
    """Wochenansicht mit Statistiken"""
    today = datetime.now(TIMEZONE).date()
    u = current_user()
    
    # Standardwerte: aktuelle Woche
    if year is None or week is None:
        # ISO-Woche verwenden
        iso_calendar = today.isocalendar()
        year = iso_calendar[0]
        week = iso_calendar[1]
    
    # Ersten Tag der Woche berechnen (Montag)
    jan_4 = datetime(year, 1, 4, tzinfo=TIMEZONE)
    week_start = jan_4 + timedelta(days=-jan_4.weekday(), weeks=week-1)
    start_date = week_start.date()
    end_date = start_date + timedelta(days=6)

    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()
    
    # Alle Entries für die Woche in einer Query holen
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
    
    # Wochentage generieren
    weekdays = []
    for i in range(7):
        day = start_date + timedelta(days=i)
        weekdays.append({
            'date': day,
            'name': day.strftime('%A'),
            'short': day.strftime('%a'),
            'day': day.day,
            'is_today': day == today
        })

    for habit in habits:
        habit_entries = entries_by_habit.get(habit.id, [])
        calendar_data[habit.id] = {e.date.isoformat(): e.completed for e in habit_entries}

        completed = sum(1 for e in habit_entries if e.completed)
        rate = (completed / 7 * 100) if completed > 0 else 0

        stats.append({
            'habit': habit,
            'rate': round(rate, 1),
            'completed': completed,
            'current_streak': StatsService.get_current_streak(habit.id, end_date),
            'longest_streak': StatsService.get_longest_streak(habit.id),
            'trend': round(StatsService.get_trend(habit.id, end_date), 1)
        })

    overall_rate = sum(s['rate'] for s in stats) / len(stats) if stats else 0

    return render_template(
        'week.html',
        stats={'habits': stats, 'overall_rate': overall_rate, 'start_date': start_date, 'end_date': end_date},
        calendar_data=calendar_data,
        weekdays=weekdays,
        year=year,
        week=week,
        today=today
    )


@app.route('/settings')
@login_required
def settings():
    u = current_user()
    habits = Habit.query.filter_by(user_id=u.id).order_by(Habit.position).all()
    
    # Benutzer-Info für Settings anzeigen
    user_info = {
        'id': u.id,
        'name': u.name,
        'habits_count': len(habits),
        'created_at': u.created_at
    }
    
    return render_template('settings.html', habits=habits, user_info=user_info)


# =========================
# API - Alle mit User-Isolation!
# =========================
@app.route('/api/habits', methods=['GET'])
@login_required
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
@login_required
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
@login_required
def api_update_habit(habit_id):
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
@login_required
def api_delete_habit(habit_id):
    u = current_user()
    habit = Habit.query.filter_by(id=habit_id, user_id=u.id).first()
    if not habit:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(habit)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/toggle', methods=['POST'])
@login_required
def api_toggle():
    u = current_user()
    data = request.get_json()
    habit_id = data.get('habit_id')
    date_str = data.get('date')
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    # Sicherheitsprüfung: Habit gehört dem aktuellen User
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
