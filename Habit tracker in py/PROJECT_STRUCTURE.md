# Habit Tracker - Projekt-Struktur

## 📁 Vollständige Dateiübersicht

```
habit-tracker/
│
├── 📄 app.py                      # Flask-Hauptanwendung
│   ├── Models (Habit, Entry)
│   ├── Routes (/, /month, /settings)
│   ├── API-Endpunkte (/api/*)
│   └── StatsService (Statistik-Berechnungen)
│
├── 📄 db_utils.py                 # Datenbank-Verwaltung CLI
│   ├── init, reset, export/import
│   └── Statistiken und Test-Daten
│
├── 📄 requirements.txt            # Python-Dependencies
├── 📄 .env.example                # Umgebungsvariablen-Template
├── 📄 .gitignore                  # Git-Ignore-Regeln
│
├── 📄 README.md                   # Hauptdokumentation
├── 📄 QUICKSTART.md               # Schnellstart-Anleitung
├── 📄 PROJECT_STRUCTURE.md        # Diese Datei
│
├── 🔧 setup.sh                    # Linux/macOS Setup-Script
├── 🔧 setup.bat                   # Windows Setup-Script
│
├── 📂 templates/                  # Jinja2 HTML-Templates
│   ├── base.html                  # Basis-Template (Header, Navigation)
│   ├── today.html                 # Tägliche Checkliste
│   ├── month.html                 # Monatsansicht mit Stats
│   └── settings.html              # Gewohnheiten-Verwaltung
│
├── 📂 static/                     # Statische Assets
│   ├── style.css                  # Styling (responsive, minimalistisch)
│   └── app.js                     # JavaScript (API-Calls, Interaktionen)
│
└── 🗄️ habits.db                   # SQLite-Datenbank (auto-generiert)
```

## 🏗️ Architektur-Übersicht

### Backend (Flask)

```
┌─────────────────────────────────────────┐
│           Flask Application             │
├─────────────────────────────────────────┤
│  Routes Layer                           │
│  ├── / (heute)                          │
│  ├── /month/<year>/<month>              │
│  └── /settings                          │
├─────────────────────────────────────────┤
│  API Layer (REST)                       │
│  ├── POST /api/toggle                   │
│  ├── GET /api/habits                    │
│  ├── POST /api/habits                   │
│  ├── PUT /api/habits/<id>               │
│  ├── DELETE /api/habits/<id>            │
│  └── GET /api/stats/<year>/<month>      │
├─────────────────────────────────────────┤
│  Business Logic                         │
│  └── StatsService                       │
│      ├── get_completion_rate()          │
│      ├── get_current_streak()           │
│      ├── get_longest_streak()           │
│      └── get_month_stats()              │
├─────────────────────────────────────────┤
│  Data Layer (SQLAlchemy ORM)           │
│  ├── Habit Model                        │
│  │   ├── id, name, category             │
│  │   ├── position, created_at           │
│  │   └── relationship: entries          │
│  └── Entry Model                        │
│      ├── id, habit_id, date             │
│      ├── completed                      │
│      └── unique constraint              │
├─────────────────────────────────────────┤
│  Database (SQLite)                      │
│  └── habits.db                          │
└─────────────────────────────────────────┘
```

### Frontend (Templates + JavaScript)

```
┌─────────────────────────────────────────┐
│         Browser Interface               │
├─────────────────────────────────────────┤
│  Templates (Jinja2)                     │
│  ├── base.html (Layout)                 │
│  ├── today.html (Checkliste)            │
│  ├── month.html (Statistiken)           │
│  └── settings.html (Verwaltung)         │
├─────────────────────────────────────────┤
│  JavaScript (app.js)                    │
│  ├── API Helper                         │
│  ├── toggleHabit()                      │
│  ├── Keyboard Navigation                │
│  └── Notification System                │
├─────────────────────────────────────────┤
│  Styling (style.css)                    │
│  ├── Responsive Grid                    │
│  ├── CSS Variables                      │
│  ├── Animations                         │
│  └── Print Styles                       │
├─────────────────────────────────────────┤
│  Charts (Chart.js)                      │
│  └── Bar Chart (Monatsansicht)          │
└─────────────────────────────────────────┘
```

## 🔄 Datenfluss

### Gewohnheit abhaken (Toggle)

```
User Click
    ↓
[JavaScript] toggleHabit()
    ↓
[Optimistic UI Update]
    ↓
POST /api/toggle
    ↓
[Flask Route] api_toggle()
    ↓
[Database] Entry.query / Create / Update
    ↓
[Response] JSON { completed: true/false }
    ↓
[JavaScript] Confirm UI State
    ↓
[Update] Progress Ring
```

### Monatsstatistiken laden

```
Page Load
    ↓
[Flask Route] month_view()
    ↓
[Service] StatsService.get_month_stats()
    ↓
[Database Queries]
    ├── Entries for date range
    ├── Calculate completion rates
    ├── Calculate streaks
    └── Calculate trends
    ↓
[Template Render] month.html
    ↓
[JavaScript] Chart.js initialization
    ↓
[Display] Statistics + Calendar Grid
```

## 📊 Datenmodell

### Entity-Relationship Diagram

```
┌─────────────────┐
│     Habit       │
├─────────────────┤
│ PK  id          │
│     name        │
│     category    │
│     position    │
│     created_at  │
└────────┬────────┘
         │ 1
         │
         │ has many
         │
         │ n
┌────────┴────────┐
│     Entry       │
├─────────────────┤
│ PK  id          │
│ FK  habit_id    │
│     date        │
│     completed   │
└─────────────────┘

Constraints:
- UNIQUE(habit_id, date)
- CASCADE DELETE
```

## 🎨 UI-Komponenten

### today.html - Checkliste
```
┌────────────────────────────────────┐
│ Header: Datum + Progress Ring      │
├────────────────────────────────────┤
│ ☐ Meditation                       │
│ ☑ Sport/Bewegung                   │
│ ☐ Gesund essen                     │
│ ☑ Wasser trinken                   │
│ ☐ Lesen                            │
│ ☐ Früh aufstehen                   │
└────────────────────────────────────┘
```

### month.html - Statistiken
```
┌────────────────────────────────────┐
│ Navigation: ← Januar 2025 →        │
├────────────────────────────────────┤
│ Gesamt-Erfüllung: 75%              │
│ ████████████████░░░░░░░░           │
├────────────────────────────────────┤
│ Meditation (80%)                   │
│ ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐    │
│ │✓│✓│ │✓│✓│✓│ │✓│✓│✓│✓│ │✓│✓│    │
│ └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘    │
│ Streak: 5 | Längs: 12 | Trend: +5%│
├────────────────────────────────────┤
│ [Bar Chart] Übersicht              │
└────────────────────────────────────┘
```

### settings.html - Verwaltung
```
┌────────────────────────────────────┐
│ Neue Gewohnheit                    │
│ [Name eingeben        ]            │
│ [Kategorie (optional) ]            │
│ [Hinzufügen]                       │
├────────────────────────────────────┤
│ Vorhandene Gewohnheiten            │
│ ⋮⋮ Meditation       ✎ 🗑          │
│ ⋮⋮ Sport/Bewegung   ✎ 🗑          │
│ ⋮⋮ Gesund essen     ✎ 🗑          │
└────────────────────────────────────┘
```

## 🔧 Konfiguration

### .env Variablen
```ini
SECRET_KEY          # Flask Secret (32+ Zeichen)
FLASK_ENV           # development/production
DATABASE_URL        # SQLite-Pfad
TIMEZONE            # pytz timezone string
WEEK_START          # 0=Monday, 6=Sunday
DEFAULT_HABITS      # Komma-getrennt
```

### CSS Variablen (style.css)
```css
--primary-color     # Hauptfarbe (grün)
--secondary-color   # Akzentfarbe (blau)
--background        # Hintergrund
--surface           # Karten-Hintergrund
--text-primary      # Haupttext
--text-secondary    # Sekundärtext
--border            # Rahmen
--success/warning/error
```

## 🚀 Deployment-Optionen

### Entwicklung
```bash
python app.py
# http://localhost:5000
```

### Produktion mit Gunicorn
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]
```

### Systemd Service
```ini
[Unit]
Description=Habit Tracker
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/habit-tracker
Environment="PATH=/var/www/habit-tracker/venv/bin"
ExecStart=/var/www/habit-tracker/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app

[Install]
WantedBy=multi-user.target
```

## 🔐 Sicherheitsfeatures

- **CSRF-Schutz**: Flask-WTF Token-Validierung
- **SQL Injection**: SQLAlchemy ORM mit Parametrisierung
- **XSS**: Jinja2 Auto-Escaping
- **Input Validation**: Server-seitige Prüfung
- **Secure Headers**: Content-Security-Policy (optional)

## 📈 Performance-Optimierungen

### Datenbank
- Indizes auf `habit_id` und `date`
- Unique Constraint für schnelle Lookups
- Lazy Loading für Relationships

### Frontend
- CSS/JS Minification (Produktion)
- Caching-Header für statische Assets
- Optimistic UI Updates
- Lazy Chart Rendering

### API
- JSON-Response (klein, schnell)
- Efficient Queries (JOINs)
- Connection Pooling

## 🧪 Testing-Strategien

### Unit Tests (Beispiel)
```python
def test_completion_rate():
    # Test StatsService.get_completion_rate()
    pass

def test_streak_calculation():
    # Test StatsService.get_current_streak()
    pass
```

### Integration Tests
```python
def test_toggle_api():
    # Test POST /api/toggle
    pass

def test_month_stats_api():
    # Test GET /api/stats/<year>/<month>
    pass
```

### E2E Tests (Selenium/Playwright)
```python
def test_user_workflow():
    # 1. Open today page
    # 2. Toggle habit
    # 3. Check progress update
    # 4. Navigate to month view
    # 5. Verify statistics
    pass
```

## 📝 Code-Konventionen

### Python (PEP 8)
- 4 Leerzeichen Einrückung
- Snake_case für Funktionen/Variablen
- PascalCase für Klassen
- Docstrings für Funktionen

### JavaScript
- 2 Leerzeichen Einrückung
- camelCase für Variablen
- Async/Await für API-Calls
- JSDoc Kommentare

### CSS
- BEM-ähnliche Namenskonvention
- Mobile-First Media Queries
- CSS Variablen für Theming
- Logische Gruppierung

## 🔄 Erweiterungsmöglichkeiten

### Geplante Features
- [ ] Multi-User Support mit Login
- [ ] Export als PDF/CSV
- [ ] Push-Notifications
- [ ] Habit-Kategorien filtern
- [ ] Dark Mode
- [ ] Streak-Belohnungen
- [ ] Wöchentliche Reports
- [ ] API-Rate-Limiting
- [ ] Offline-Support (PWA)
- [ ] Mobile Apps (React Native)

### Plugin-Architektur
```python
# plugins/reminder.py
class ReminderPlugin:
    def daily_reminder(self):
        # E-Mail/Push notification
        pass
```

---

**Version:** 1.0.0  
**Letzte Aktualisierung:** 2025-09-30  
**Lizenz:** MIT