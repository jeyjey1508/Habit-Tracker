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

// -----------------------------
// LocalStorage Persistence Layer
// -----------------------------
const LOCAL_KEY_ENTRIES = 'ht_entries_v1';   // { habitId: { 'YYYY-MM-DD': true/false, ... }, ... }
const LOCAL_KEY_PENDING = 'ht_pending_v1';   // [ { habit_id, date, completed, ts }, ... ]

function loadLocalEntries() {
    try {
        return JSON.parse(localStorage.getItem(LOCAL_KEY_ENTRIES) || '{}');
    } catch (e) {
        console.warn('Failed to parse local entries', e);
        return {};
    }
}

function saveLocalEntries(obj) {
    try {
        localStorage.setItem(LOCAL_KEY_ENTRIES, JSON.stringify(obj));
    } catch (e) {
        console.error('Failed to save local entries', e);
    }
}

function saveLocalEntry(habitId, date, completed) {
    const e = loadLocalEntries();
    const id = String(habitId);
    if (!e[id]) e[id] = {};
    e[id][date] = !!completed;
    saveLocalEntries(e);
}

function loadPending() {
    try {
        return JSON.parse(localStorage.getItem(LOCAL_KEY_PENDING) || '[]');
    } catch (e) {
        console.warn('Failed to parse pending queue', e);
        return [];
    }
}

function savePending(arr) {
    try {
        localStorage.setItem(LOCAL_KEY_PENDING, JSON.stringify(arr));
    } catch (e) {
        console.error('Failed to save pending queue', e);
    }
}

function addPendingToggle(habitId, date, completed) {
    const p = loadPending();
    p.push({ habit_id: habitId, date, completed: !!completed, ts: Date.now() });
    savePending(p);
}

async function flushPending() {
    const queue = loadPending();
    if (!queue.length) return;
    // try to flush in order. If any request fails (network/403), stop to avoid repeated failures.
    const remaining = [];
    for (const item of queue) {
        try {
            // Try to get current server state first (not strictly necessary), then post toggle if needed.
            // We POST /api/toggle which flips server state; server endpoint returns completed boolean.
            const res = await api.post('/api/toggle', { habit_id: item.habit_id, date: item.date });
            if (res && typeof res.completed !== 'undefined') {
                // Update local storage to match server response
                saveLocalEntry(item.habit_id, item.date, res.completed);
            } else {
                // Invalid response — keep in queue
                remaining.push(item);
            }
        } catch (e) {
            console.warn('flushPending: stopping due to error', e);
            // Re-queue this and all remaining
            remaining.push(item);
            // append remaining items of queue (they will be retried later)
            const idx = queue.indexOf(item);
            for (let j = idx + 1; j < queue.length; j++) remaining.push(queue[j]);
            break;
        }
    }
    savePending(remaining);
}

// try to flush every minute
setInterval(flushPending, 60_000);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') flushPending(); });

// -----------------------------
// UI helpers: apply local entries to DOM
// -----------------------------
function applyLocalEntriesToDOM() {
    const local = loadLocalEntries();
    // Find any elements that have data-habit-id and data-date attributes (today, week cells)
    document.querySelectorAll('[data-habit-id][data-date]').forEach(el => {
        const habitId = String(el.dataset.habitId);
        const date = el.dataset.date;
        // If server already rendered it as completed, prefer server (keep as is).
        if (el.classList.contains('completed')) {
            // ensure local copy matches server
            saveLocalEntry(habitId, date, true);
            return;
        }
        // If local has an entry for that habit/date, apply it
        if (local[habitId] && local[habitId][date]) {
            el.classList.add('completed');
            // If there's a button inside, update ARIA attributes
            const btn = el.querySelector('button.habit-checkbox, .habit-checkbox');
            if (btn) {
                try {
                    btn.setAttribute('aria-pressed', 'true');
                    btn.setAttribute('aria-label', `${btn.getAttribute('aria-label') || ''}`.trim());
                } catch (e) {}
            }
        }
    });

    // For Today page: if there are list items without date attr (today supplies ul[data-date]), handle them
    const habitList = document.getElementById('habitList');
    if (habitList && habitList.dataset.date) {
        const date = habitList.dataset.date;
        habitList.querySelectorAll('.habit-item[data-habit-id]').forEach(li => {
            const id = String(li.dataset.habitId);
            if (local[id] && local[id][date]) {
                li.classList.add('completed');
                const btn = li.querySelector('button.habit-checkbox');
                if (btn) {
                    try { btn.setAttribute('aria-pressed', 'true'); } catch (e) {}
                    try { btn.setAttribute('aria-label', `${btn.getAttribute('aria-label') || ''}`.trim()); } catch (_) {}
                }
            }
        });
    }
}

// -----------------------------
// Robustere toggleHabit: ignoriert nicht-interaktive Elemente und verhindert Errors
// -----------------------------
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

        // Save server-confirmed state to local storage
        saveLocalEntry(habitId, date, !!data.completed);

        // If any pending queue existed for this habit/date, try to flush (cleanup)
        // flushPending will update/remove items as needed
        flushPending();

        // If an updateProgress function exists (today view), call it
        if (typeof updateProgress === 'function') {
            try { updateProgress(); } catch (_) {}
        }

    } catch (error) {
        // Revert optimistic UI change on error
        if (habitItem) habitItem.classList.toggle('completed', wasCompleted);

        // Save to local queue for later sync
        addPendingToggle(habitId, date, !wasCompleted);
        // Also save to local entries (so UI reflects the user's intention)
        saveLocalEntry(habitId, date, !wasCompleted);

        showNotification('Offline: Änderung lokal gespeichert. Wir versuchen später zu synchronisieren.', 'info');
        console.error('toggleHabit error (saved locally):', error);
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
        background: ${type === 'error' ? '#f44336' : (type === 'info' ? '#2196F3' : '#4CAF50')};
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

// On load: apply local entries and try to flush pending queue
document.addEventListener('DOMContentLoaded', () => {
    try {
        applyLocalEntriesToDOM();
        // Try a first flush (non-blocking)
        flushPending().catch(e => { /* ignore */ });
    } catch (e) {
        console.error('Error during local init', e);
    }
});

// Export to window for debugging (no module system assumed)
window.HabitTracker = window.HabitTracker || {};
window.HabitTracker.api = api;
window.HabitTracker.toggleHabit = toggleHabit;
window.HabitTracker.showNotification = showNotification;
window.HabitTracker._localEntries = loadLocalEntries();
