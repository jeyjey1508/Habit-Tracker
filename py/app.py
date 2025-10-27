import os
from flask import Flask, session, redirect, url_for

app = Flask(__name__)

# ...

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Loggt den aktuellen Benutzer aus und löscht die Session-User-Information."""
    # Entferne den user-Eintrag aus der Session
    session.pop('user', None)
    # Optional: session.clear() wenn du wirklich alle Session-Daten löschen willst
    # session.clear()
    return redirect(url_for('index'))

# ...

if __name__ == '__main__':
    app.run()