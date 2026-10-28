/**
 * Devengers Global Authentication & Notification Helper.
 * Handles session checking, navbar updates with real avatar photos, 2FA OTP,
 * role-based security lockdown, and real-time community notifications across all pages.
 */

window.DevengersAuth = {
    currentUser: null,

    applyFastCachedState() {
        try {
            const cached = localStorage.getItem('devengers_user_session');
            if (cached) {
                const user = JSON.parse(cached);
                this.currentUser = user;
                this.applyRoleRestrictions(user);
                this.updateNavbar(user);
                return;
            }
        } catch (e) {}
        this.updateNavbar(null);
    },

    async checkSession() {
        try {
            const token = localStorage.getItem('devengers_token');
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            const res = await fetch('/api/auth/me', { headers });
            if (res.ok) {
                const data = await res.json();
                if (data.authenticated && data.user) {
                    this.currentUser = data.user;
                    if (data.token && !localStorage.getItem('devengers_token')) {
                        try { localStorage.setItem('devengers_token', data.token); } catch(e) {}
                    }
                    try {
                        localStorage.setItem('devengers_user_session', JSON.stringify(data.user));
                    } catch(e) {}
                    this.applyRoleRestrictions(data.user);
                    this.updateNavbar(data.user);
                    if (window.DevengersNotifications) {
                        window.DevengersNotifications.fetchNotifications();
                    }
                    return data.user;
                } else if (!this.currentUser) {
                    this.updateNavbar(null);
                }
            }
            if (res && res.status === 401) {
                this.currentUser = null;
                try {
                    localStorage.removeItem('devengers_user_session');
                    localStorage.removeItem('devengers_token');
                } catch(e) {}
                this.applyRoleRestrictions(null);
                this.updateNavbar(null);
            }
        } catch (e) {
            console.warn('[DevengersAuth] Session check failed:', e);
        }
        return this.currentUser;
    },

    /**
     * Strictly hides or removes all admin sections, admin studio links, and delete controls
     * for users who are NOT authenticated as an administrator.
     */
    applyRoleRestrictions(user) {
        const isAdmin = user && user.role === 'admin';

        if (document.body) {
            if (isAdmin) {
                document.body.classList.add('is-admin');
            } else {
                document.body.classList.remove('is-admin');
            }
        }

        // 1. Target all admin link elements and sections
        const adminElements = document.querySelectorAll(
            'a[href^="admin-"], a[href*="/admin-"], .admin-only, [data-admin-only], #admin-nav-item, #admin-studio-link, .admin-section, #admin-portal-link'
        );
        adminElements.forEach(el => {
            if (isAdmin) {
                el.classList.remove('hidden');
                el.style.display = '';
            } else {
                el.classList.add('hidden');
                el.style.display = 'none';
            }
        });

        // 2. Target delete options across the site - strictly hidden from members
        const deleteControls = document.querySelectorAll(
            '[data-admin-delete], .admin-delete-btn, .btn-admin-delete, #pv-delete-btn, #modal-delete-proj-btn, .delete-btn, button[data-action="delete"]'
        );
        deleteControls.forEach(el => {
            if (isAdmin) {
                el.classList.remove('hidden');
                el.style.display = '';
            } else {
                el.classList.add('hidden');
                el.style.display = 'none';
            }
        });

        // 3. Guard against unauthorized page visits on admin pages
        const currentPage = window.location.pathname.split('/').pop();
        if (currentPage.startsWith('admin-')) {
            if (!isAdmin) {
                console.warn('[DevengersAuth] Unauthorized access attempt to admin page. Redirecting to login.');
                window.location.replace(`login.html?redirect=${encodeURIComponent(currentPage)}`);
            }
        }
    },

    updateNavbar(user) {
        const profileBtns = document.querySelectorAll('.nav-profile-btn');
        const loginLinks = document.querySelectorAll('a[href="login.html"]');
        const signupLinks = document.querySelectorAll('a[href="register.html"]');

        // Set active state on current page link consistently
        let currentPage = window.location.pathname.split('/').pop() || 'index.html';
        if (!currentPage || currentPage === '') currentPage = 'index.html';
        const navLinks = document.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href === currentPage) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });

        if (user) {
            // Update Profile button with real uploaded picture inside Instagram Story Ring
            profileBtns.forEach(btn => {
                btn.href = 'profile.html';
                btn.setAttribute('title', `My Profile (${user.name || user.email})`);
                
                const initials = (user.name || user.email || 'D').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
                const rawUrl = (user.avatar_url || '').trim();
                const avatarSrc = rawUrl ? (rawUrl.startsWith('http') || rawUrl.startsWith('/') ? rawUrl : '/' + rawUrl) : null;

                btn.innerHTML = '';
                const inner = document.createElement('span');
                inner.className = 'nav-profile-inner';
                inner.title = user.name || 'User';

                if (avatarSrc) {
                    const img = document.createElement('img');
                    img.src = avatarSrc;
                    img.alt = user.name || 'Profile';
                    img.className = 'w-full h-full object-cover rounded-full';
                    img.onerror = function() {
                        inner.innerHTML = `<span class="nav-avatar-initials">${initials}</span>`;
                    };
                    inner.appendChild(img);
                } else {
                    inner.innerHTML = `<span class="nav-avatar-initials">${initials}</span>`;
                }
                btn.appendChild(inner);
            });

            // Replace Login with Logout
            loginLinks.forEach(link => {
                link.innerHTML = 'LOGOUT';
                link.href = '#';
                link.setAttribute('title', `Logged in as ${user.email} (${user.role || 'member'})`);
                link.onclick = (e) => {
                    e.preventDefault();
                    this.logout();
                };
            });

            // Hide Sign up button when logged in
            signupLinks.forEach(link => {
                link.classList.add('hidden');
            });
        } else {
            profileBtns.forEach(btn => {
                btn.href = 'profile.html';
                btn.setAttribute('title', 'My Profile (Sign In)');
                btn.innerHTML = `
                    <span class="nav-profile-inner">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                        </svg>
                    </span>
                `;
            });

            loginLinks.forEach(link => {
                link.innerHTML = 'LOGIN';
                link.href = 'login.html';
                link.onclick = null;
            });

            signupLinks.forEach(link => {
                link.classList.remove('hidden');
            });
        }

        // Render responsive mobile navigation drawer
        this.renderMobileDrawer(user);
    },

    renderMobileDrawer(user) {
        const fixedNav = document.querySelector('.devengers-navbar-fixed');
        const notch = document.querySelector('.devengers-navbar-notch');
        if (!notch) return;

        // 1. Ensure hamburger button exists in notch
        let menuBtn = document.getElementById('devengers-mobile-menu-btn');
        if (!menuBtn) {
            menuBtn = document.createElement('button');
            menuBtn.type = 'button';
            menuBtn.id = 'devengers-mobile-menu-btn';
            menuBtn.className = 'md:hidden flex items-center justify-center w-9 h-9 rounded-full bg-black/60 text-white border border-white/20 hover:border-[#CDFF29] transition-all active:scale-95 cursor-pointer ml-1.5 shrink-0 shadow-sm';
            menuBtn.setAttribute('aria-label', 'Toggle Navigation Menu');
            menuBtn.innerHTML = `
                <div class="hamburger-box">
                    <span class="hamburger-bar bar-top"></span>
                    <span class="hamburger-bar bar-mid"></span>
                    <span class="hamburger-bar bar-bot"></span>
                </div>
            `;
            menuBtn.onclick = (e) => {
                e.stopPropagation();
                this.toggleMobileDrawer();
            };

            // Append to the right cluster in the notch
            const rightCluster = notch.querySelector('.flex.items-center:last-child') || notch;
            rightCluster.appendChild(menuBtn);
        }

        // 2. Ensure mobile drawer container exists in fixedNav
        let drawer = document.getElementById('devengers-mobile-drawer');
        if (!drawer && fixedNav) {
            drawer = document.createElement('div');
            drawer.id = 'devengers-mobile-drawer';
            drawer.className = 'drawer-closed';
            fixedNav.appendChild(drawer);

            // Click outside closes drawer
            document.addEventListener('click', (e) => {
                if (drawer && !drawer.contains(e.target) && menuBtn && !menuBtn.contains(e.target)) {
                    drawer.classList.remove('drawer-open');
                    drawer.classList.add('drawer-closed');
                    if (menuBtn) menuBtn.classList.remove('menu-open');
                }
            });
        }

        if (!drawer) return;

        let currentPage = window.location.pathname.split('/').pop() || 'index.html';
        if (!currentPage || currentPage === '') currentPage = 'index.html';

        const links = [
            { label: 'Events', href: 'events.html', icon: '⚡' },
            { label: 'Learn', href: 'learn.html', icon: '📚' },
            { label: 'Campus Resource', href: 'campus.html', icon: '🎓' },
            { label: 'DSA Streak', href: 'dsa.html', icon: '🔥' },
            { label: 'Gallery', href: 'gallery.html', icon: '🖼️' },
            { label: 'Certificates', href: 'certificates.html', icon: '📜' },
            { label: 'Jobs', href: 'jobs.html', icon: '💼' },
            { label: 'Directory', href: 'directory.html', icon: '👥' },
        ];

        let linksHtml = links.map(l => {
            const isActive = l.href === currentPage ? 'active' : '';
            return `<a href="${l.href}" class="mobile-drawer-link ${isActive}"><span>${l.label}</span><span class="text-xs">${l.icon}</span></a>`;
        }).join('');

        let authSectionHtml = '';
        if (user) {
            const rawDrawerUrl = (user.avatar_url || '').trim();
            const drawerAvatarSrc = rawDrawerUrl ? (rawDrawerUrl.startsWith('http') || rawDrawerUrl.startsWith('/') ? rawDrawerUrl : '/' + rawDrawerUrl) : null;
            const drawerAvatarHtml = drawerAvatarSrc
                ? `<img src="${drawerAvatarSrc}" alt="Avatar" class="w-5 h-5 rounded-full object-cover border border-[#CDFF29]/40 shrink-0">`
                : `<span class="w-5 h-5 rounded-full bg-[#CDFF29]/20 text-[#CDFF29] flex items-center justify-center text-[10px] font-mono font-bold shrink-0">⚡</span>`;

            authSectionHtml = `
                <div class="pt-3 mt-2 border-t border-zinc-800 flex flex-col gap-2">
                    <a href="profile.html" class="flex items-center justify-between px-3 py-2 rounded-xl bg-white/5 border border-white/10 hover:border-[#CDFF29] text-xs font-mono font-bold text-white transition-colors">
                        <div class="flex items-center gap-2 truncate">
                            ${drawerAvatarHtml}
                            <span class="truncate">${this.escape(user.name || user.email)}</span>
                        </div>
                        <span class="text-[10px] text-[#CDFF29] uppercase tracking-wider shrink-0">Profile &rarr;</span>
                    </a>
                    <button type="button" onclick="window.DevengersAuth.logout()" class="w-full py-2 rounded-xl bg-red-950/60 hover:bg-red-900 border border-red-800 text-red-300 text-xs font-mono font-bold uppercase tracking-wider transition-colors cursor-pointer text-center">
                        LOGOUT
                    </button>
                </div>
            `;
        } else {
            authSectionHtml = `
                <div class="pt-3 mt-2 border-t border-zinc-800 grid grid-cols-2 gap-2">
                    <a href="login.html" class="text-center py-2 rounded-xl bg-black/60 border border-zinc-700 text-white text-xs font-bold uppercase tracking-wider hover:border-white transition-colors">
                        LOGIN
                    </a>
                    <a href="register.html" class="text-center py-2 rounded-xl bg-[#CDFF29] text-black text-xs font-bold uppercase tracking-wider hover:bg-white transition-colors shadow-sm">
                        SIGN UP
                    </a>
                </div>
            `;
        }

        drawer.innerHTML = `
            <div class="flex flex-col gap-1">
                ${linksHtml}
                ${authSectionHtml}
            </div>
        `;
    },

    toggleMobileDrawer() {
        const drawer = document.getElementById('devengers-mobile-drawer');
        const menuBtn = document.getElementById('devengers-mobile-menu-btn');
        if (!drawer) return;
        const isOpen = drawer.classList.contains('drawer-open');
        if (isOpen) {
            drawer.classList.remove('drawer-open');
            drawer.classList.add('drawer-closed');
            if (menuBtn) menuBtn.classList.remove('menu-open');
        } else {
            drawer.classList.remove('drawer-closed');
            drawer.classList.add('drawer-open');
            if (menuBtn) menuBtn.classList.add('menu-open');
        }
    },

    async login(email, password, otp = null) {
        try {
            const payload = { email, password };
            if (otp) {
                payload.otp = otp;
            }
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            
            if (data.requires_otp) {
                return {
                    requires_otp: true,
                    message: data.message,
                    dev_otp: data.dev_otp
                };
            }

            if (res.ok && data.success) {
                if (data.token) {
                    localStorage.setItem('devengers_token', data.token);
                }
                if (data.user) {
                    try {
                        localStorage.setItem('devengers_user_session', JSON.stringify(data.user));
                    } catch(e) {}
                }
                this.currentUser = data.user;
                return { success: true, user: data.user, redirect: data.redirect };
            }
            return { success: false, error: data.error || 'Invalid credentials' };
        } catch (err) {
            return { success: false, error: 'Network connection failed. Please try again.' };
        }
    },

    async sendPasswordResetOtp(email) {
        try {
            const res = await fetch('/api/auth/send-otp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: (email || '').trim().toLowerCase(), purpose: 'Password Reset' })
            });
            const data = await res.json();
            return data;
        } catch (err) {
            return { success: false, error: 'Network connection failed. Please try again.' };
        }
    },

    async resetPassword(email, otp, newPassword, confirmPassword) {
        try {
            const res = await fetch('/api/auth/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: (email || '').trim().toLowerCase(),
                    otp: (otp || '').trim(),
                    password: newPassword,
                    confirm_password: confirmPassword || newPassword
                })
            });
            const data = await res.json();
            return data;
        } catch (err) {
            return { success: false, error: 'Network connection failed. Please try again.' };
        }
    },

    async logout() {
        try {
            await fetch('/api/auth/logout', { method: 'POST' });
        } catch (e) {}
        try {
            localStorage.removeItem('devengers_token');
            localStorage.removeItem('devengers_user_session');
        } catch(e) {}
        this.currentUser = null;
        window.location.href = 'login.html';
    },

    async requireAdmin() {
        const user = await this.checkSession();
        if (!user || user.role !== 'admin') {
            const currentPage = window.location.pathname.split('/').pop();
            window.location.replace(`login.html?redirect=${encodeURIComponent(currentPage)}`);
            return null;
        }
        return user;
    }
};

/**
 * Real-time Notifications Client.
 * Displays unread indicators and a floating dropdown across every page.
 * Synchronizes with database and localStorage for instant, reliable state persistence.
 */
window.DevengersNotifications = {
    notifications: [],
    unreadCount: 0,
    isOpen: false,
    pollTimer: null,

    async fetchNotifications() {
        try {
            const res = await fetch('/api/notifications');
            if (res.ok) {
                const data = await res.json();
                if (data.success) {
                    const rawList = data.notifications || [];
                    const readSet = new Set(JSON.parse(localStorage.getItem('devengers_read_notifs') || '[]'));
                    
                    this.notifications = rawList.map(n => {
                        const isRead = Boolean(n.is_read || readSet.has(n.id));
                        return { ...n, is_read: isRead };
                    });

                    this.unreadCount = this.notifications.filter(n => !n.is_read).length;
                    this.updateUI();
                }
            }
        } catch (e) {
            console.warn('[DevengersNotifications] Fetch failed:', e);
        }
    },

    updateUI() {
        const dots = document.querySelectorAll('.nav-notification-dot, #nav-notification-dot');
        dots.forEach(dot => {
            if (this.unreadCount > 0) {
                dot.classList.remove('hidden');
                dot.style.display = 'block';
            } else {
                dot.classList.add('hidden');
                dot.style.display = 'none';
            }
        });

        const panel = document.getElementById('nav-notifications-dropdown');
        if (panel && this.isOpen) {
            this.renderList(panel);
        }
    },

    toggleDropdown(e) {
        if (e) e.stopPropagation();
        this.isOpen = !this.isOpen;
        let panel = document.getElementById('nav-notifications-dropdown');
        if (!panel) {
            panel = this.createDropdown();
        }
        if (this.isOpen) {
            this.renderList(panel);
            panel.classList.remove('hidden');
        } else {
            panel.classList.add('hidden');
        }
    },

    createDropdown() {
        let panel = document.getElementById('nav-notifications-dropdown');
        if (panel) return panel;

        panel = document.createElement('div');
        panel.id = 'nav-notifications-dropdown';
        panel.className = 'fixed md:absolute top-20 md:top-12 right-4 md:right-0 w-[calc(100vw-32px)] md:w-96 max-h-[480px] bg-[#121216] border-2 border-white/20 rounded-3xl shadow-2xl z-[100] flex flex-col overflow-hidden text-white backdrop-blur-2xl hidden';
        
        // Find notification button or place in body
        const btn = document.querySelector('.nav-notification-btn, #nav-notification-btn, [title="Notifications"]');
        if (btn && btn.parentElement) {
            btn.parentElement.classList.add('relative');
            btn.parentElement.appendChild(panel);
        } else {
            document.body.appendChild(panel);
        }

        // Close on click outside
        document.addEventListener('click', (ev) => {
            if (this.isOpen && !panel.contains(ev.target) && (!btn || !btn.contains(ev.target))) {
                this.isOpen = false;
                panel.classList.add('hidden');
            }
        });

        return panel;
    },

    renderList(panel) {
        let itemsHtml = '';
        if (this.notifications.length === 0) {
            itemsHtml = `
                <div class="py-12 px-6 text-center text-gray-500 font-mono text-xs">
                    <span class="text-3xl block mb-2">🔔</span>
                    No notifications right now.
                </div>
            `;
        } else {
            itemsHtml = this.notifications.map(n => {
                const isUnread = !n.is_read;
                const icon = n.type === 'comment' ? '💬' : (n.type === 'event' ? '🎯' : (n.type === 'system' ? '🛡️' : '🚀'));
                return `
                    <a href="${n.link_url || '#'}" onclick="window.DevengersNotifications.handleItemClick('${n.id}', '${n.link_url || '#'}', event)" class="p-3.5 border-b border-white/5 hover:bg-white/5 transition-colors flex items-start gap-3 text-left ${isUnread ? 'bg-[#7B42F6]/20' : ''}">
                        <span class="text-lg shrink-0 mt-0.5">${icon}</span>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between gap-2">
                                <h4 class="text-xs font-bold text-white font-mono truncate">${this.escape(n.title)}</h4>
                                ${isUnread ? '<span class="w-2.5 h-2.5 rounded-full bg-[#CDFF29] shrink-0 animate-pulse"></span>' : ''}
                            </div>
                            <p class="text-[11px] text-gray-300 font-mono mt-0.5 leading-snug line-clamp-2">${this.escape(n.message)}</p>
                            <span class="text-[9px] font-mono text-gray-500 mt-1 block">${this.timeAgo(n.created_at)}</span>
                        </div>
                    </a>
                `;
            }).join('');
        }

        panel.innerHTML = `
            <div class="p-4 border-b border-white/10 flex items-center justify-between bg-black/50">
                <div class="flex items-center gap-2">
                    <span class="text-sm">🔔</span>
                    <h3 class="text-xs font-mono font-bold text-white uppercase tracking-wider">Notifications</h3>
                    ${this.unreadCount > 0 ? `<span class="bg-[#CDFF29] text-black text-[10px] font-mono font-bold px-1.5 py-0.2 rounded-full">${this.unreadCount}</span>` : ''}
                </div>
                ${this.unreadCount > 0 ? `
                    <button type="button" onclick="window.DevengersNotifications.markAllRead()" class="text-[10px] font-mono text-[#CDFF29] hover:underline uppercase cursor-pointer">
                        Mark read
                    </button>
                ` : ''}
            </div>
            <div class="overflow-y-auto max-h-[380px]">
                ${itemsHtml}
            </div>
        `;
    },

    async markAllRead() {
        const readSet = new Set(JSON.parse(localStorage.getItem('devengers_read_notifs') || '[]'));
        this.notifications.forEach(n => {
            n.is_read = true;
            readSet.add(n.id);
        });
        localStorage.setItem('devengers_read_notifs', JSON.stringify(Array.from(readSet)));
        this.unreadCount = 0;
        this.updateUI();

        try {
            await fetch('/api/notifications/mark-read', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ all: true })
            });
        } catch (e) {}
    },

    async handleItemClick(id, url, e) {
        const readSet = new Set(JSON.parse(localStorage.getItem('devengers_read_notifs') || '[]'));
        readSet.add(id);
        localStorage.setItem('devengers_read_notifs', JSON.stringify(Array.from(readSet)));

        const notif = this.notifications.find(n => n.id === id);
        if (notif && !notif.is_read) {
            notif.is_read = true;
            this.unreadCount = Math.max(0, this.unreadCount - 1);
            this.updateUI();
        }

        try {
            await fetch('/api/notifications/mark-read', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ notification_ids: [id] })
            });
        } catch (e) {}

        if (url && url !== '#' && !url.startsWith('javascript:')) {
            window.location.href = url;
        }
    },

    escape(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    },

    timeAgo(dateStr) {
        try {
            const date = new Date(dateStr);
            const seconds = Math.floor((new Date() - date) / 1000);
            if (seconds < 60) return 'Just now';
            const minutes = Math.floor(seconds / 60);
            if (minutes < 60) return `${minutes}m ago`;
            const hours = Math.floor(minutes / 60);
            if (hours < 24) return `${hours}h ago`;
            const days = Math.floor(hours / 24);
            return `${days}d ago`;
        } catch (e) {
            return 'Recently';
        }
    }
};

// Auto check session, zero-flicker cached render, and 25s live poll
(function() {
    function init() {
        window.DevengersAuth.applyFastCachedState();
        window.DevengersAuth.checkSession();
        if (!window.DevengersNotifications.pollTimer) {
            window.DevengersNotifications.pollTimer = setInterval(() => {
                window.DevengersNotifications.fetchNotifications();
            }, 25000);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

