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
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return await response.json();
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

// Habit Toggle Function
async function toggleHabit(habitId, date, button) {
    const habitItem = button.closest('.habit-item');
    const wasCompleted = habitItem.classList.contains('completed');
    
    // Optimistic UI update
    habitItem.classList.toggle('completed');
    
    try {
        const data = await api.post('/api/toggle', {
            habit_id: habitId,
            date: date
        });
        
        // Confirm UI state matches server
        habitItem.classList.toggle('completed', data.completed);
        
        // Update ARIA label
        const habitName = habitItem.querySelector('.habit-name').textContent;
        button.setAttribute('aria-label', 
            `${habitName} ${data.completed ? 'erledigt' : 'nicht erledigt'}`
        );
        
        // Update progress if on today page
        if (typeof updateProgress === 'function') {
            updateProgress();
        }
    } catch (error) {
        // Revert on error
        habitItem.classList.toggle('completed', wasCompleted);
        showNotification('Fehler beim Speichern', 'error');
    }
}

// Notification System
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        padding: 1rem 1.5rem;
        background: ${type === 'error' ? '#f44336' : '#4CAF50'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Add animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(400px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(400px); opacity: 0; }
    }
`;
document.head.appendChild(style);

// Keyboard Navigation
document.addEventListener('keydown', (e) => {
    // Space to toggle focused habit
    if (e.code === 'Space' && e.target.classList.contains('habit-checkbox')) {
        e.preventDefault();
        e.target.click();
    }
    
    // Arrow keys to navigate habits
    if (['ArrowUp', 'ArrowDown'].includes(e.code)) {
        const habits = Array.from(document.querySelectorAll('.habit-checkbox'));
        const currentIndex = habits.indexOf(document.activeElement);
        
        if (currentIndex !== -1) {
            e.preventDefault();
            const nextIndex = e.code === 'ArrowDown' 
                ? Math.min(currentIndex + 1, habits.length - 1)
                : Math.max(currentIndex - 1, 0);
            habits[nextIndex].focus();
        }
    }
});

// Service Worker for offline support (optional enhancement)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        // Uncomment to enable offline support
        // navigator.serviceWorker.register('/static/sw.js');
    });
}

// Export for use in templates
window.api = api;
window.toggleHabit = toggleHabit;
window.showNotification = showNotification;