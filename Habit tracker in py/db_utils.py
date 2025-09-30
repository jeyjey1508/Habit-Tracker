#!/usr/bin/env python3
"""
Database Utility Script for Habit Tracker
Provides commands for database management and data import/export
"""

import sys
from datetime import datetime, timedelta
import json
import csv
from app import app, db, Habit, Entry, TIMEZONE

def init_database():
    """Initialize database with tables"""
    with app.app_context():
        db.create_all()
        print("✓ Database tables created")

def reset_database():
    """Reset database (WARNING: Deletes all data!)"""
    with app.app_context():
        response = input("⚠️  This will delete ALL data. Continue? (yes/no): ")
        if response.lower() == 'yes':
            db.drop_all()
            db.create_all()
            print("✓ Database reset complete")
        else:
            print("✗ Operation cancelled")

def add_default_habits():
    """Add default habits if none exist"""
    with app.app_context():
        if Habit.query.count() == 0:
            default_habits = [
                ('Meditation', 'Achtsamkeit'),
                ('Sport/Bewegung', 'Gesundheit'),
                ('Gesund essen', 'Gesundheit'),
                ('Wasser trinken', 'Gesundheit'),
                ('Lesen', 'Bildung'),
                ('Früh aufstehen', 'Produktivität')
            ]
            
            for i, (name, category) in enumerate(default_habits):
                habit = Habit(name=name, category=category, position=i)
                db.session.add(habit)
            
            db.session.commit()
            print(f"✓ Added {len(default_habits)} default habits")
        else:
            print(f"✓ {Habit.query.count()} habits already exist")

def export_to_json(filename='backup.json'):
    """Export all data to JSON"""
    with app.app_context():
        data = {
            'habits': [],
            'entries': [],
            'export_date': datetime.now(TIMEZONE).isoformat()
        }
        
        for habit in Habit.query.all():
            data['habits'].append({
                'id': habit.id,
                'name': habit.name,
                'category': habit.category,
                'position': habit.position
            })
        
        for entry in Entry.query.all():
            data['entries'].append({
                'habit_id': entry.habit_id,
                'date': entry.date.isoformat(),
                'completed': entry.completed
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Exported {len(data['habits'])} habits and {len(data['entries'])} entries to {filename}")

def import_from_json(filename='backup.json'):
    """Import data from JSON backup"""
    with app.app_context():
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Clear existing data
            Entry.query.delete()
            Habit.query.delete()
            db.session.commit()
            
            # Import habits
            habit_map = {}
            for h in data['habits']:
                habit = Habit(
                    name=h['name'],
                    category=h.get('category'),
                    position=h['position']
                )
                db.session.add(habit)
                db.session.flush()
                habit_map[h['id']] = habit.id
            
            # Import entries
            for e in data['entries']:
                entry = Entry(
                    habit_id=habit_map[e['habit_id']],
                    date=datetime.fromisoformat(e['date']).date(),
                    completed=e['completed']
                )
                db.session.add(entry)
            
            db.session.commit()
            print(f"✓ Imported {len(data['habits'])} habits and {len(data['entries'])} entries")
        
        except FileNotFoundError:
            print(f"✗ File not found: {filename}")
        except Exception as e:
            print(f"✗ Import failed: {e}")
            db.session.rollback()

def export_to_csv(filename='habits_export.csv'):
    """Export entries to CSV for analysis"""
    with app.app_context():
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Habit', 'Category', 'Date', 'Completed', 'Weekday'])
            
            entries = Entry.query.join(Habit).order_by(Entry.date.desc()).all()
            
            for entry in entries:
                writer.writerow([
                    entry.habit.name,
                    entry.habit.category or '',
                    entry.date.isoformat(),
                    'Yes' if entry.completed else 'No',
                    entry.date.strftime('%A')
                ])
            
            print(f"✓ Exported {len(entries)} entries to {filename}")

def show_statistics():
    """Display database statistics"""
    with app.app_context():
        total_habits = Habit.query.count()
        total_entries = Entry.query.count()
        completed_entries = Entry.query.filter_by(completed=True).count()
        
        print("\n📊 Database Statistics")
        print("=" * 40)
        print(f"Total Habits: {total_habits}")
        print(f"Total Entries: {total_entries}")
        print(f"Completed Entries: {completed_entries}")
        
        if total_entries > 0:
            completion_rate = (completed_entries / total_entries) * 100
            print(f"Overall Completion Rate: {completion_rate:.1f}%")
        
        print("\n📋 Habits List:")
        for habit in Habit.query.order_by(Habit.position).all():
            entries_count = Entry.query.filter_by(habit_id=habit.id).count()
            completed_count = Entry.query.filter_by(habit_id=habit.id, completed=True).count()
            rate = (completed_count / entries_count * 100) if entries_count > 0 else 0
            print(f"  • {habit.name} ({habit.category or 'No category'}): {completed_count}/{entries_count} ({rate:.0f}%)")

def seed_test_data():
    """Generate test data for the past 30 days"""
    with app.app_context():
        import random
        
        if Habit.query.count() == 0:
            add_default_habits()
        
        habits = Habit.query.all()
        today = datetime.now(TIMEZONE).date()
        
        for days_ago in range(30):
            date = today - timedelta(days=days_ago)
            
            for habit in habits:
                # Random completion with 70% success rate
                if random.random() < 0.7:
                    entry = Entry.query.filter_by(habit_id=habit.id, date=date).first()
                    if not entry:
                        entry = Entry(habit_id=habit.id, date=date, completed=True)
                        db.session.add(entry)
        
        db.session.commit()
        print("✓ Generated test data for the past 30 days")

def main():
    """Main CLI interface"""
    if len(sys.argv) < 2:
        print("""
Habit Tracker - Database Utilities

Usage: python db_utils.py <command>

Commands:
  init              Initialize database tables
  reset             Reset database (deletes all data!)
  defaults          Add default habits
  stats             Show database statistics
  export-json       Export data to JSON backup
  import-json       Import data from JSON backup
  export-csv        Export entries to CSV
  seed              Generate test data (30 days)

Examples:
  python db_utils.py init
  python db_utils.py export-json backup.json
  python db_utils.py stats
        """)
        return
    
    command = sys.argv[1]
    
    commands = {
        'init': init_database,
        'reset': reset_database,
        'defaults': add_default_habits,
        'stats': show_statistics,
        'export-json': lambda: export_to_json(sys.argv[2] if len(sys.argv) > 2 else 'backup.json'),
        'import-json': lambda: import_from_json(sys.argv[2] if len(sys.argv) > 2 else 'backup.json'),
        'export-csv': lambda: export_to_csv(sys.argv[2] if len(sys.argv) > 2 else 'habits_export.csv'),
        'seed': seed_test_data
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"✗ Unknown command: {command}")
        print("Run without arguments to see available commands")

if __name__ == '__main__':
    main()