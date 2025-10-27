// Global CSRF Token
const getCsrfToken = () => {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
};

// API Helper
const api = {
    async request(url, options = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
            ...options.headers
        };

        try {
            const response = await fetch(url, { ...options, headers });
            if (!response.ok) {
                // Try to extract JSON error message if present
                let errMsg = `HTTP error! status: ${response.status}`;
                try {
                    const json = await response.json();
                    if (json && json.error) errMsg += ` - ${json.error}`;
                } catch (_) {}
                throw new Error(errMsg);
            }
            // Some endpoints may return no content
            const text = await response.text();
            try {
                return text ? JSON.parse(text) : {};
            } catch (_) {
                return text;
            }
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    get(url) {
        return this.request(url);
    },

    post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },

    put(url, data) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    delete(url) {
        return this.request(url, { method: 'DELETE' });
    }
};

// Robustere toggleHabit: ignoriert nicht-interaktive Elemente und verhindert Errors
async function toggleHabit(habitId, date, button) {
    // Defensive checks
    if (!button) {
        console.warn('toggleHabit: kein Button-Element übergeben');
        return;
    }
    // If button is marked disabled (used in week view), do nothing
    if (button.classList.contains('disabled')) {
        return;
    }

    const habitItem = button.closest('.habit-item');
    if (!habitItem) {
        console.warn('toggleHabit: .habit-item nicht gefunden für Button', button);
        return;
    }

    const wasCompleted = habitItem.classList.contains('completed');

    // Optimistic UI update
    habitItem.classList.toggle('completed');

    try {
        const data = await api.post('/api/toggle', {
            habit_id: habitId,
            date: date
        });

        // If backend returned an error structure, throw it
        if (!data || typeof data.completed === 'undefined') {
            throw new Error('Ungültige Serverantwort beim Toggle');
        }

        // Confirm UI state with server response
        habitItem.classList.toggle('completed', !!data.completed);

        // Update ARIA attributes
        const habitNameEl = habitItem.querySelector('.habit-name') || habitItem.querySelector('strong');
        const habitName = habitNameEl ? habitNameEl.textContent.trim() : '';
        try {
            button.setAttribute('aria-label', `${habitName} ${data.completed ? 'erledigt' : 'nicht erledigt'}`);
            button.setAttribute('aria-pressed', data.completed ? 'true' : 'false');
        } catch (e) {
            // ignore DOM setAttribute errors
        }

        // If an updateProgress function exists (today view), call it
        if (typeof updateProgress === 'function') {
            try { updateProgress(); } catch (_) {}
        }

    } catch (error) {
        // Revert optimistic UI change on error
        if (habitItem) habitItem.classList.toggle('completed', wasCompleted);
        showNotification('Fehler beim Speichern', 'error');
        console.error('toggleHabit error:', error);
    }
}

// Notification System
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    // Inline styles to keep this component self-contained
    notification.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'error' ? '#f44336' : '#4CAF50'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.28s ease;
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.animation = 'slideOut 0.28s ease';
        setTimeout(() => notification.remove(), 320);
    }, 2800);
}

// Add small animation styles for notifications
(function addNotificationStyles(){
    if (document.getElementById('ht-notif-styles')) return;
    const style = document.createElement('style');
    style.id = 'ht-notif-styles';
    style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(200px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(200px); opacity: 0; }
    }
    .notification { font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; font-size: 14px; }
    `;
    document.head.appendChild(style);
})();

// Utility: simple debounce (if needed elsewhere)
function debounce(fn, wait = 200) {
    let t;
    return function(...args) {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), wait);
    };
}

// Export to window for debugging (no module system assumed)
window.HabitTracker = window.HabitTracker || {};
window.HabitTracker.api = api;
window.HabitTracker.toggleHabit = toggleHabit;
window.HabitTracker.showNotification = showNotification;
