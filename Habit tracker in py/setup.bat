@echo off
echo ================================
echo    Habit Tracker Setup
echo ================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python nicht gefunden! Bitte installiere Python 3.8+
    pause
    exit /b 1
)

echo [OK] Python gefunden
echo.

REM Create virtual environment
echo [1/4] Erstelle virtuelle Umgebung...
python -m venv venv
if errorlevel 1 (
    echo [ERROR] Fehler beim Erstellen der virtuellen Umgebung
    pause
    exit /b 1
)
echo [OK] Virtuelle Umgebung erstellt
echo.

REM Activate virtual environment
echo [2/4] Aktiviere virtuelle Umgebung...
call venv\Scripts\activate.bat
echo.

REM Install dependencies
echo [3/4] Installiere Abhängigkeiten...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fehler bei der Installation
    pause
    exit /b 1
)
echo [OK] Abhängigkeiten installiert
echo.

REM Create .env file
echo [4/4] Konfiguriere Umgebungsvariablen...
if not exist .env (
    copy .env.example .env
    echo [OK] .env Datei erstellt
) else (
    echo [OK] .env Datei existiert bereits
)
echo.

echo ================================
echo    Setup abgeschlossen!
echo ================================
echo.
echo Zum Starten der Anwendung:
echo   1. venv\Scripts\activate
echo   2. python app.py
echo.
echo Dann oeffne: http://localhost:5000
echo.
pause