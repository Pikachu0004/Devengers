/**
 * Devengers Global Theme Controller: Dark Obsidian <-> Peach Cream Eye Comfort
 */
(function() {
    const THEME_STORAGE_KEY = 'devengers_theme';

    // Apply saved theme immediately to prevent flashing
    function initTheme() {
        const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || 'dark';
        applyTheme(savedTheme);
    }

    function applyTheme(theme) {
        const root = document.documentElement;
        const body = document.body;
        if (theme === 'peach') {
            root.setAttribute('data-theme', 'peach');
            root.classList.add('theme-peach');
            if (body) {
                body.setAttribute('data-theme', 'peach');
                body.classList.add('theme-peach');
            }
        } else {
            root.removeAttribute('data-theme');
            root.classList.remove('theme-peach');
            if (body) {
                body.removeAttribute('data-theme');
                body.classList.remove('theme-peach');
            }
        }
        updateToggleButtons(theme);
    }

    function toggleTheme() {
        const current = localStorage.getItem(THEME_STORAGE_KEY) || 'dark';
        const nextTheme = current === 'peach' ? 'dark' : 'peach';
        localStorage.setItem(THEME_STORAGE_KEY, nextTheme);
        applyTheme(nextTheme);
        return nextTheme;
    }

    function updateToggleButtons(theme) {
        const toggles = document.querySelectorAll('.theme-toggle-btn');
        toggles.forEach(btn => {
            const isPeach = theme === 'peach';
            btn.setAttribute('aria-pressed', isPeach ? 'true' : 'false');
            btn.setAttribute('title', isPeach ? 'Switch to Dark Obsidian Theme' : 'Switch to Peach Cream Eye Comfort Theme');
            
            const thumb = btn.querySelector('.toggle-thumb');
            if (thumb) {
                if (isPeach) {
                    thumb.style.transform = 'translateX(24px)';
                    thumb.innerHTML = '🍑';
                    btn.classList.add('bg-[#FFD9C0]', 'border-[#FF6B35]');
                    btn.classList.remove('bg-black/60', 'border-gray-700');
                } else {
                    thumb.style.transform = 'translateX(0px)';
                    thumb.innerHTML = '🌙';
                    btn.classList.remove('bg-[#FFD9C0]', 'border-[#FF6B35]');
                    btn.classList.add('bg-black/60', 'border-gray-700');
                }
            }
        });
    }

    // Expose global controller
    window.DevengersTheme = {
        getTheme: () => localStorage.getItem(THEME_STORAGE_KEY) || 'dark',
        setTheme: (t) => { localStorage.setItem(THEME_STORAGE_KEY, t); applyTheme(t); },
        toggleTheme: toggleTheme,
        applyTheme: applyTheme
    };

    // Run immediately
    initTheme();

    document.addEventListener('DOMContentLoaded', () => {
        const current = localStorage.getItem(THEME_STORAGE_KEY) || 'dark';
        applyTheme(current);
    });
})();
