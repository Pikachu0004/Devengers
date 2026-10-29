"""
Devengers HTTP & REST API Server.
Zero external dependencies - powered by Python's standard library and SQLite.
Serves static frontend, handles authentication, and powers the Events management system.
"""

import http.server
import socketserver
import os
import sys
import json
import urllib.parse
import uuid
import re
import secrets
from datetime import datetime, timezone
from http import cookies

from db import (
    init_db, get_connection, seed_starter_events_if_empty,
    seed_starter_courses_if_empty, get_courses, get_course,
    create_course, update_course, delete_course,
    get_learn_settings, update_learn_settings,
    toggle_user_course_progress, get_user_completed_courses, get_user_completed_course_ids,
    toggle_user_application, get_user_applied_events, get_user_applied_event_ids,
    get_user_full_profile, update_user_profile,
    log_user_questions_solved, log_study_activity, get_user_study_heatmap,
    toggle_user_dsa_problem, get_user_dsa_progress,
    log_daily_user_checkin, calculate_user_streak
)
import db
from auth import authenticate, create_session, get_session_user, delete_session, create_or_update_user, generate_and_store_otp, verify_otp, authenticate_or_create_google_user, reset_user_password, normalize_purpose
import campus_service
import dsa_service
import gallery_service
import certificate_service
import base64


PORT = int(os.environ.get("PORT", "3000"))
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(DIRECTORY, "Assest", "uploads")
ALLOWED_CATEGORIES = {'Hackathons', 'Quizzes', 'Internships', 'Jobs'}
ALLOWED_STATUSES = {'Draft', 'Published', 'Unpublished', 'Archived'}

def is_safe_url(url: str) -> bool:
    """Validates that a destination URL is http or https, preventing unsafe schemes."""
    if not url:
        return False
    u = url.strip()
    return bool(re.match(r'^https?://', u, re.IGNORECASE))

def validate_image_magic(data: bytes) -> str | None:
    """Validates actual file bytes for common image types without trusting file extension."""
    if len(data) < 12:
        return None
    # PNG
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    # JPEG
    if data[:3] == b'\xff\xd8\xff':
        return 'jpg'
    # WebP: starts with RIFF, contains WEBP at byte 8-12
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    # GIF (optional support)
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    return None

# ------------------ Cyber Security Hardening & Rate Limiter ------------------
_RATE_LIMIT_STORE = {}

def is_rate_limited(client_ip: str, limit: int = 15, window_sec: int = 60) -> bool:
    """Sliding-window rate limiter to protect authentication and API endpoints against brute-force attacks."""
    if client_ip in ("127.0.0.1", "localhost", "::1"):
        limit = max(limit, 120)
    now = datetime.now(timezone.utc).timestamp()
    history = _RATE_LIMIT_STORE.get(client_ip, [])
    history = [t for t in history if now - t < window_sec]
    if len(history) >= limit:
        _RATE_LIMIT_STORE[client_ip] = history
        return True
    history.append(now)
    _RATE_LIMIT_STORE[client_ip] = history
    return False

class DevengersHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    @staticmethod
    def is_blocked_path(raw_path: str) -> bool:
        """Cyber defense: blocks access to sensitive files, hidden directories, databases, source code, and path traversal."""
        clean = raw_path.replace('\\', '/').split('?')[0].split('#')[0].strip()
        parts = [p.lower() for p in clean.split('/') if p]

        # Block path traversal attempts
        if '..' in clean:
            return True

        # Block hidden files and directories (e.g., .env, .git, .DS_Store, etc.)
        if any(p.startswith('.') for p in parts):
            return True

        # Block SQLite and database files
        if any(clean.lower().endswith(ext) for ext in ('.db', '.sqlite', '.sqlite3', '.sql')):
            return True

        # Block python backend source code and bytecode
        if any(clean.lower().endswith(ext) for ext in ('.py', '.pyc', '.pyo', '.pyd')):
            return True

        # Block environment, credential, and certificate files
        if any(clean.lower().endswith(ext) for ext in ('.env', '.key', '.pem', '.cert', '.crt', '.token', '.bak', '.dump')):
            return True

        # Block python bytecode directories, internal caches, and private dependencies
        if any(p in ('__pycache__', 'venv', '.venv', 'node_modules') for p in parts) or '__pycache__' in clean:
            return True

        return False

    # ------------------ Utility Helpers ------------------

    def send_json(self, data, status_code=200, extra_headers=None):
        payload = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Connection', 'close')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def read_json_body(self) -> dict:
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def get_current_user(self) -> dict | None:
        """Extracts user from devengers_session cookie or Authorization header."""
        # Check Cookie
        cookie_header = self.headers.get('Cookie')
        token = None
        if cookie_header:
            c = cookies.SimpleCookie()
            try:
                c.load(cookie_header)
                if 'devengers_session' in c:
                    token = c['devengers_session'].value
            except Exception:
                pass

        # Check Authorization header fallback
        if not token:
            auth_header = self.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:].strip()

        if token:
            return get_session_user(token)
        return None

    def require_admin(self) -> tuple[dict | None, bool]:
        """Ensures request is authenticated as an administrator."""
        user = self.get_current_user()
        if not user or user.get('role') != 'admin':
            self.send_json({"error": "Unauthorized: Administrator access required."}, 401)
            return None, False
        return user, True

    def send_error(self, code, message=None, explain=None):
        if code == 500:
            error_file = os.path.join(DIRECTORY, '500.html')
            if os.path.exists(error_file):
                self.send_response(500)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                with open(error_file, 'rb') as f:
                    content = f.read()
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
        elif code == 404:
            not_found_file = os.path.join(DIRECTORY, '404.html')
            if os.path.exists(not_found_file):
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                with open(not_found_file, 'rb') as f:
                    content = f.read()
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
        super().send_error(code, message, explain)

    # ------------------ Overridden Static & Caching ------------------

    def end_headers(self):
        # Force cache-busting on all responses during local testing
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')

        # Cyber Defense & Browser Security Headers
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        super().end_headers()

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Cyber attack defense: block sensitive resources
        if self.is_blocked_path(path):
            self.send_error(403, "Access Denied: Protected System Resource")
            return

        # UptimeRobot / health-check: respond 200 OK for any /api/ HEAD request
        # without executing the full handler (HEAD must not send a body)
        if path.startswith('/api/'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            return

        if path in ('/', '/index'):
            self.send_response(302)
            self.send_header('Location', '/index.html')
            self.end_headers()
            return
        if path in ('/500', '/error/500', '/simulate-500'):
            error_file = os.path.join(DIRECTORY, '500.html')
            if os.path.exists(error_file):
                self.send_response(500)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(os.path.getsize(error_file)))
                self.end_headers()
                return
        if path in ('/404', '/error/404'):
            not_found_file = os.path.join(DIRECTORY, '404.html')
            if os.path.exists(not_found_file):
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(os.path.getsize(not_found_file)))
                self.end_headers()
                return
        super().do_HEAD()

    # ------------------ HTTP Method Dispatchers ------------------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Cyber attack defense: block sensitive files from being read/downloaded
        if self.is_blocked_path(path):
            self.send_error(403, "Access Denied: Protected System Resource")
            return

        # 1. Root redirect to /index.html
        if path in ('/', '/index'):
            self.send_response(302)
            self.send_header('Location', '/index.html')
            self.end_headers()
            return

        # 1a. Explicit 500 error page route / test endpoint
        if path in ('/500', '/error/500', '/simulate-500'):
            error_file = os.path.join(DIRECTORY, '500.html')
            if os.path.exists(error_file):
                self.send_response(500)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                with open(error_file, 'rb') as f:
                    content = f.read()
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # 1b. Explicit 404 error page route
        if path in ('/404', '/error/404'):
            not_found_file = os.path.join(DIRECTORY, '404.html')
            if os.path.exists(not_found_file):
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                with open(not_found_file, 'rb') as f:
                    content = f.read()
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # 2. Public API: Current Session Profile
        if path == '/api/auth/me':
            cookie_header = self.headers.get('Cookie')
            token = None
            if cookie_header:
                c = cookies.SimpleCookie()
                try:
                    c.load(cookie_header)
                    if 'devengers_session' in c:
                        token = c['devengers_session'].value
                except Exception:
                    pass
            if not token:
                auth_header = self.headers.get('Authorization', '')
                if auth_header.startswith('Bearer '):
                    token = auth_header[7:].strip()
            user = get_session_user(token) if token else None
            if user:
                self.send_json({"authenticated": True, "user": user, "token": token})
            else:
                self.send_json({"authenticated": False, "user": None})
            return

        # 2a. Public API: Google OAuth Config
        if path == '/api/auth/google/config':
            self.send_json({"client_id": os.environ.get("DEVENGERS_GOOGLE_CLIENT_ID", "")})
            return

        # 2b. User Profile API
        if path == '/api/user/profile':
            self.handle_get_user_profile()
            return

        # 2c. User Course Completion Tracking
        if path == '/api/user/course-progress':
            self.handle_get_user_course_progress()
            return

        # 2d. User Applications Tracking (Jobs, Internships, Events)
        if path == '/api/user/applications':
            self.handle_get_user_applications()
            return

        # 3. Public API: List Published Events
        if path == '/api/events':
            self.handle_public_events(query)
            return

        # 3b. Public API: List Courses & Learn Resources
        if path == '/api/courses':
            self.handle_public_courses(query)
            return

        # 3c. Public API: List University PYQs & Campus Curriculum
        if path == '/api/pyqs':
            self.handle_get_pyqs(query)
            return

        # 3d. Public API: DSA Sheet (Arrays to DP)
        if path == '/api/dsa/sheet':
            self.send_json({"success": True, "data": dsa_service.get_dsa_catalog()})
            return

        # 3e. Public API: Problem of the Day (POTD)
        if path == '/api/dsa/potd':
            self.send_json({"success": True, "potd": dsa_service.get_potd()})
            return

        # 3f. User API: DSA Progress (Solved & Revision)
        if path == '/api/user/dsa-progress':
            user = self.get_current_user()
            if not user:
                self.send_json({"success": True, "authenticated": False, "solved": [], "revision": [], "heatmap": {}, "max_streak": 1})
                return
            progress = get_user_dsa_progress(user["id"])
            profile = get_user_full_profile(user["id"])
            self.send_json({
                "success": True,
                "authenticated": True,
                "solved": progress["solved"],
                "revision": progress["revision"],
                "streak": profile.get("streak_count", 1),
                "max_streak": max(profile.get("streak_count", 1), 1),
                "questions_solved_total": profile.get("questions_solved_total", 0),
                "heatmap": profile.get("heatmap", {})
            })
            return

        # Clean URL & Legacy Aliases
        if path in ('/social.html', '/events'):
            self.path = '/events.html'
            super().do_GET()
            return

        if path in ('/articles.html', '/campus', '/resources'):
            self.path = '/campus.html'
            super().do_GET()
            return

        if path in ('/pricing.html', '/dsa-streak.html', '/streak.html', '/dsa'):
            self.path = '/dsa.html'
            super().do_GET()
            return

        if path in ('/learn', '/courses'):
            self.path = '/learn.html'
            super().do_GET()
            return

        if path in ('/gallery',):
            self.path = '/gallery.html'
            super().do_GET()
            return

        if path in ('/certificates',):
            self.path = '/certificates.html'
            super().do_GET()
            return

        if path in ('/directory',):
            self.path = '/directory.html'
            super().do_GET()
            return

        if path in ('/jobs', '/careers'):
            self.path = '/jobs.html'
            super().do_GET()
            return

        if path in ('/login',):
            self.path = '/login.html'
            super().do_GET()
            return

        if path in ('/forgot-password', '/reset-password'):
            self.path = '/forgot-password.html'
            super().do_GET()
            return

        if path in ('/register', '/signup'):
            self.path = '/register.html'
            super().do_GET()
            return

        if path in ('/profile',):
            self.path = '/profile.html'
            super().do_GET()
            return

        if path == '/robots.txt':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            with open(os.path.join(DIRECTORY, 'robots.txt'), 'rb') as f:
                content = f.read()
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == '/sitemap.xml':
            self.send_response(200)
            self.send_header('Content-Type', 'application/xml; charset=utf-8')
            with open(os.path.join(DIRECTORY, 'sitemap.xml'), 'rb') as f:
                content = f.read()
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        # Assets typo tolerance (/assets/ -> /Assest/)
        if path.startswith('/assets/'):
            self.path = '/Assest/' + path[len('/assets/'):]
            super().do_GET()
            return

        # 4. Public API: Single Event Detail
        if path.startswith('/api/events/'):
            event_id = path[len('/api/events/'):]
            self.handle_public_single_event(event_id)
            return

        # 4c. Public API: Certificates Competitions
        if path == '/api/certificates/competitions':
            self.send_json({"success": True, "competitions": certificate_service.get_public_competitions()})
            return

        # 4c2. User Certificates API
        if path == '/api/certificates/my-certificates':
            user = self.get_current_user()
            email = query.get('email', [''])[0] if query else ''
            if not email and user:
                email = user.get('email', '')
            if not email:
                self.send_json({"success": True, "certificates": []})
                return
            certs = certificate_service.get_user_certificates(email)
            self.send_json({"success": True, "certificates": certs, "email": email})
            return

        # 4c3. Public / User API: Notifications
        if path == '/api/notifications':
            user = self.get_current_user()
            user_id = user['id'] if user else None
            notifs, unread = db.get_notifications_for_user(user_id)
            self.send_json({"success": True, "notifications": notifs, "unread_count": unread})
            return

        # 4c4. Admin API: Get pushed notifications
        if path == '/api/admin/notifications':
            user, ok = self.require_admin()
            if not ok:
                return
            items = db.get_all_broadcast_notifications()
            self.send_json({"success": True, "notifications": items})
            return


        # 4d. Admin API: Certificate Competitions
        if path == '/api/admin/certificates':
            user, ok = self.require_admin()
            if not ok:
                return
            self.send_json({"success": True, "competitions": certificate_service.get_admin_competitions()})
            return

        if path.startswith('/api/admin/certificates/') and path.endswith('/participants'):
            comp_id = path[len('/api/admin/certificates/'):-len('/participants')]
            user, ok = self.require_admin()
            if not ok:
                return
            self.send_json({"success": True, **certificate_service.get_competition_participants(comp_id)})
            return

        if path.startswith('/api/admin/certificates/') and not path.endswith('/participants'):
            comp_id = path[len('/api/admin/certificates/'):]
            user, ok = self.require_admin()
            if not ok:
                return
            comp = certificate_service.get_admin_competition(comp_id)
            if not comp:
                self.send_json({"error": "Competition not found"}, 404)
                return
            self.send_json({"success": True, "competition": comp})
            return

        if path == '/api/admin/certificates-issues':
            user, ok = self.require_admin()
            if not ok:
                return
            self.send_json({"success": True, "issues": certificate_service.get_all_issues()})
            return

        # 5. Admin API: List All Events with Stats
        if path == '/api/admin/events':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_admin_events(query)
            return

        # 5b. Admin API: List All Courses with Stats
        if path == '/api/admin/courses':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_admin_courses(query)
            return

        # 6. Admin API: Single Event for Editing
        if path.startswith('/api/admin/events/'):
            user, ok = self.require_admin()
            if not ok:
                return
            event_id = path[len('/api/admin/events/'):]
            self.handle_admin_single_event(event_id)
            return

        # 6b. Admin API: Learn Settings
        if path == '/api/admin/learn/settings':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_get_learn_settings()
            return

        # 6c. Admin API: Single Course for Editing
        if path.startswith('/api/admin/courses/'):
            user, ok = self.require_admin()
            if not ok:
                return
            course_id = path[len('/api/admin/courses/'):]
            self.handle_admin_single_course(course_id)
            return

        # 7. Admin API: Job & Internship Sync Status
        if path == '/api/admin/jobs/sync-status':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_sync_status()
            return

        # 8. Admin API: Campus Summary
        if path == '/api/admin/campus/summary':
            user, ok = self.require_admin()
            if not ok:
                return
            self.send_json({"success": True, "summary": campus_service.get_campus_summary()})
            return

        # 9. Admin API: Campus Universities
        if path == '/api/admin/campus/universities':
            user, ok = self.require_admin()
            if not ok:
                return
            catalog = campus_service.get_catalog_data()
            self.send_json({"success": True, "universities": catalog.get("universities", [])})
            return

        # 10. Admin API: Campus Curriculum
        if path == '/api/admin/campus/curriculum':
            user, ok = self.require_admin()
            if not ok:
                return
            catalog = campus_service.get_catalog_data()
            self.send_json({"success": True, "curriculum": catalog.get("curriculum", {})})
            return

        # 11. Admin API: Campus Papers List
        if path == '/api/admin/campus/papers':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_admin_campus_papers(query)
            return

        # 12. Admin API: Single Campus Paper
        if path.startswith('/api/admin/campus/papers/'):
            user, ok = self.require_admin()
            if not ok:
                return
            paper_id = path[len('/api/admin/campus/papers/'):]
            catalog = campus_service.get_catalog_data()
            paper = next((p for p in catalog.get("papers", []) if p["id"] == paper_id), None)
            if not paper:
                self.send_json({"error": "Paper not found"}, 404)
                return
            self.send_json({"success": True, "paper": paper})
            return

        # 13. Gallery Posters API (Auto Horizontal Advertising Banner)
        if path == '/api/gallery/posters':
            only_active = query.get("all", ["0"])[0] != "1"
            self.send_json({"success": True, "posters": gallery_service.get_posters(only_active=only_active)})
            return

        if path == '/api/admin/gallery/posters':
            user, ok = self.require_admin()
            if not ok:
                return
            self.send_json({"success": True, "posters": gallery_service.get_posters(only_active=False)})
            return

        # 14. Previous Events API (Replaces On the Web)
        if path == '/api/gallery/previous-events':
            self.send_json({"success": True, "events": gallery_service.get_previous_events()})
            return

        if path == '/api/admin/gallery/previous-events':
            user, ok = self.require_admin()
            if not ok:
                return
            self.send_json({"success": True, "events": gallery_service.get_previous_events()})
            return

        # 15. Community Projects API (Publicly browseable, managed by logged-in users & admin)
        if path == '/api/community/projects':
            search = query.get("search", [None])[0]
            category = query.get("category", [None])[0]
            self.send_json({"success": True, "projects": gallery_service.get_community_projects(search=search, category=category)})
            return

        if path.startswith('/api/community/projects/') and path.endswith('/comments'):
            proj_id = path[len('/api/community/projects/'):-len('/comments')]
            self.send_json({"success": True, "comments": gallery_service.get_project_comments(proj_id)})
            return

        if path.startswith('/api/community/projects/'):
            proj_id = path[len('/api/community/projects/'):]
            proj = gallery_service.get_community_project(proj_id)
            if not proj:
                self.send_json({"error": "Project not found"}, 404)
                return
            comments = gallery_service.get_project_comments(proj_id)
            self.send_json({"success": True, "project": proj, "comments": comments})
            return

        # 16. User My Projects API
        if path == '/api/user/my-projects':
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Unauthorized"}, 401)
                return
            self.send_json({"success": True, "projects": gallery_service.get_user_projects(user["id"])})
            return

        # Check if static file exists, else serve custom 404
        clean_path = urllib.parse.unquote(path.lstrip('/'))
        file_path = os.path.join(DIRECTORY, clean_path)
        if clean_path and not os.path.exists(file_path) and not path.startswith('/api/'):
            not_found_file = os.path.join(DIRECTORY, '404.html')
            if os.path.exists(not_found_file):
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                with open(not_found_file, 'rb') as f:
                    content = f.read()
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        # Default: Serve static files
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Cyber attack defense: block dangerous paths
        if self.is_blocked_path(path):
            self.send_error(403, "Access Denied: Protected System Resource")
            return

        # 0a. Auth: Send Email OTP
        if path == '/api/auth/send-otp':
            self.handle_send_otp()
            return

        # 0b. Auth: Reset Password
        if path == '/api/auth/reset-password':
            self.handle_reset_password()
            return

        # 0. Auth: Register
        if path == '/api/auth/register':
            self.handle_register()
            return

        # 1. Auth: Login
        if path == '/api/auth/login':
            self.handle_login()
            return

        # 1b. Auth: Google Sign-In
        if path == '/api/auth/google':
            self.handle_google_auth()
            return

        # 2. Auth: Logout
        if path == '/api/auth/logout':
            self.handle_logout()
            return

        # 3. Admin: Create Event
        if path == '/api/admin/events':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_create_event(user)
            return

        # 4. Admin: Upload Thumbnail
        if path == '/api/admin/upload':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_image_upload()
            return

        # 5. Admin: Update Status (Publish / Unpublish / Archive)
        match_status = re.match(r'^/api/admin/events/([a-zA-Z0-9_\-]+)/status$', path)
        if match_status:
            user, ok = self.require_admin()
            if not ok:
                return
            event_id = match_status.group(1)
            self.handle_update_event_status(event_id)
            return

        # 6. Admin: Trigger Instant Job Sync
        if path == '/api/admin/jobs/sync':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_trigger_sync()
            return

        # 7. Admin: Flash Event Auto-Fetch (Hackathon / Quiz via Link)
        if path == '/api/admin/events/flash-fetch':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_flash_fetch()
            return

        # 8. Admin: Create Course / Resource
        if path == '/api/admin/courses':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_create_course()
            return

        # 9. Admin: Reseed Starter Courses
        if path == '/api/admin/courses/seed':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_reseed_courses()
            return

        # 10. Admin: Update Course Status (Published, Draft, Archived)
        match_course_status = re.match(r'^/api/admin/courses/([a-zA-Z0-9_\-]+)/status$', path)
        if match_course_status:
            user, ok = self.require_admin()
            if not ok:
                return
            course_id = match_course_status.group(1)
            self.handle_update_course_status(course_id)
            return

        # 11. Admin: Update Learn Settings (Paid Coming Soon configs)
        if path == '/api/admin/learn/settings':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_update_learn_settings()
            return

        # 12. User: Toggle Course Completion / Progress Tick
        if path == '/api/user/course-progress':
            self.handle_toggle_course_progress()
            return

        # 13. User: Toggle Applied Opportunity (Job, Internship, Hackathon, Quiz)
        if path == '/api/user/applications':
            self.handle_toggle_application()
            return

        # 14. User: Log Study Activity & Questions Solved (Heatmap)
        if path == '/api/user/study-activity':
            self.handle_log_study_activity()
            return

        # 15. Admin: Save University (Add or Edit)
        if path == '/api/admin/campus/university':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_save_university()
            return

        # 16. Admin: Save Curriculum (Add or Edit Semester Curriculum)
        if path == '/api/admin/campus/curriculum':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_save_curriculum()
            return

        # 17. Admin: Save / Upload Paper (Add or Edit Paper)
        if path == '/api/admin/campus/paper':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_save_paper()
            return

        # 18. Admin: Upload PDF Question Paper File
        if path == '/api/admin/campus/upload-pdf':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_campus_pdf_upload()
            return

        # 19. User: Toggle DSA Problem (Solved or Revision)
        if path == '/api/user/dsa-progress':
            self.handle_toggle_dsa_progress()
            return

        # 20. User: Update Profile (POST support)
        if path == '/api/user/profile':
            self.handle_update_user_profile()
            return

        # 21. User: Daily Streak Check-in
        if path == '/api/user/checkin':
            self.handle_user_daily_checkin()
            return

        # 22. User: Upload Avatar or Banner Image (Multipart or Base64 JSON)
        if path == '/api/user/upload-media':
            self.handle_user_media_upload()
        # 23. Admin: Gallery Posters Create
        if path == '/api/admin/gallery/posters':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_gallery_posters_create()
            return

        # 24. Admin: Previous Events Create
        if path == '/api/admin/gallery/previous-events':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_previous_events_create()
            return

        # 25. User: Community Projects Create (Logged-in members)
        if path == '/api/community/projects':
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Login required to publish community projects"}, 401)
                return
            self.handle_community_project_create(user)
            return

        # 26. User: Community Project Comments / Chat (Logged-in members)
        match_comment = re.match(r'^/api/community/projects/([a-zA-Z0-9_\-]+)/comments$', path)
        if match_comment:
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Login required to comment or ask questions"}, 401)
                return
            proj_id = match_comment.group(1)
            self.handle_community_project_comment_create(proj_id, user)
            return

        # 27. User / Admin: Gallery Image Upload (with crop support)
        if path in ('/api/gallery/upload', '/api/upload'):
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Login required to upload media"}, 401)
                return
        # 28. Public: Verify & Fetch Certificate
        if path == '/api/certificates/verify':
            self.handle_certificate_verify()
            return

        # 29. Public: Report Issue on Certificate
        if path == '/api/certificates/report-issue':
            self.handle_certificate_report_issue()
            return

        # 29b. Notifications: Mark as Read
        if path == '/api/notifications/mark-read':
            user = self.get_current_user()
            body = self.read_json_body()
            user_id = user['id'] if user else 'guest'
            notification_ids = body.get('notification_ids')
            db.mark_notifications_read(user_id, notification_ids)
            self.send_json({"success": True})
            return

        # 29c. Notifications: Admin Push Broadcast
        if path == '/api/admin/notifications/push':
            user, ok = self.require_admin()
            if not ok:
                return
            body = self.read_json_body()
            title = body.get('title', '').strip()
            message = body.get('message', '').strip()
            link_url = body.get('link_url', '#').strip()
            n_type = body.get('type', 'announcement').strip()
            if not title or not message:
                self.send_json({"error": "Title and message are required"}, 400)
                return
            nid = db.create_notification(title, message, link_url, n_type=n_type, user_id=None)
            self.send_json({"success": True, "notification_id": nid, "message": "Notification broadcast dispatched successfully!"})
            return

        # 29d. Notifications: Admin Delete Notification
        if path.startswith('/api/admin/notifications/delete/'):
            user, ok = self.require_admin()
            if not ok:
                return
            nid = path[len('/api/admin/notifications/delete/'):].strip()
            deleted = db.delete_notification(nid)
            self.send_json({"success": deleted})
            return

        # 30. Admin: Upload Certificate Template (Image with Magic Bytes & Crop)
        if path == '/api/admin/certificates/upload-template':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_certificate_template_upload()
            return

        # 31. Admin: Create/Save Certificate Competition
        if path == '/api/admin/certificates':
            user, ok = self.require_admin()
            if not ok:
                return
            self.handle_certificate_save(user)
            return

        # 32. Admin: Upload Participant Roster (Excel / CSV)
        if path.startswith('/api/admin/certificates/') and path.endswith('/upload-roster'):
            user, ok = self.require_admin()
            if not ok:
                return
            comp_id = path[len('/api/admin/certificates/'):-len('/upload-roster')]
            self.handle_certificate_roster_upload(comp_id)
            return

        self.send_json({"error": "Not Found"}, 404)

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Admin: Update Certificate Competition
        match_cert = re.match(r'^/api/admin/certificates/([a-zA-Z0-9_\-]+)$', path)
        if match_cert:
            user, ok = self.require_admin()
            if not ok:
                return
            comp_id = match_cert.group(1)
            self.handle_certificate_update(comp_id, user)
            return

        # User: Update Profile Details, Streak & Avatar
        if path == '/api/user/profile':
            self.handle_update_user_profile()
            return

        # Admin: Edit Event
        match_event = re.match(r'^/api/admin/events/([a-zA-Z0-9_\-]+)$', path)
        if match_event:
            user, ok = self.require_admin()
            if not ok:
                return
            event_id = match_event.group(1)
            self.handle_update_event(event_id, user)
            return

        # Admin: Edit Course
        match_course = re.match(r'^/api/admin/courses/([a-zA-Z0-9_\-]+)$', path)
        if match_course:
            user, ok = self.require_admin()
            if not ok:
                return
            course_id = match_course.group(1)
            self.handle_update_course(course_id)
            return

        # Admin: Edit Gallery Poster
        match_poster = re.match(r'^/api/admin/gallery/posters/([a-zA-Z0-9_\-]+)$', path)
        if match_poster:
            user, ok = self.require_admin()
            if not ok:
                return
            poster_id = match_poster.group(1)
            self.handle_gallery_posters_update(poster_id)
            return

        # Admin: Edit Previous Event
        match_pe = re.match(r'^/api/admin/gallery/previous-events/([a-zA-Z0-9_\-]+)$', path)
        if match_pe:
            user, ok = self.require_admin()
            if not ok:
                return
            event_id = match_pe.group(1)
            self.handle_previous_events_update(event_id)
            return

        # User / Admin: Edit Community Project
        match_cp = re.match(r'^/api/community/projects/([a-zA-Z0-9_\-]+)$', path)
        if match_cp:
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Unauthorized"}, 401)
                return
            proj_id = match_cp.group(1)
            self.handle_community_project_update(proj_id, user)
            return

        self.send_json({"error": "Not Found"}, 404)


    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Admin: Delete Notification
        match_notif = re.match(r'^/api/admin/notifications/([a-zA-Z0-9_\-]+)$', path)
        if match_notif:
            user, ok = self.require_admin()
            if not ok:
                return
            nid = match_notif.group(1)
            deleted = db.delete_notification(nid)
            self.send_json({"success": deleted})
            return

        # Admin: Delete Certificate Competition
        match_cert = re.match(r'^/api/admin/certificates/([a-zA-Z0-9_\-]+)$', path)
        if match_cert:
            user, ok = self.require_admin()
            if not ok:
                return
            comp_id = match_cert.group(1)
            certificate_service.delete_competition(comp_id)
            self.send_json({"success": True})
            return

        # Admin: Delete Event
        match_event = re.match(r'^/api/admin/events/([a-zA-Z0-9_\-]+)$', path)
        if match_event:
            user, ok = self.require_admin()
            if not ok:
                return
            event_id = match_event.group(1)
            self.handle_delete_event(event_id)
            return

        # Admin: Delete Course
        match_course = re.match(r'^/api/admin/courses/([a-zA-Z0-9_\-]+)$', path)
        if match_course:
            user, ok = self.require_admin()
            if not ok:
                return
            course_id = match_course.group(1)
            self.handle_delete_course(course_id)
            return

        # Admin: Delete Campus University
        match_uni = re.match(r'^/api/admin/campus/universities/([a-zA-Z0-9_\-]+)$', path)
        if match_uni:
            user, ok = self.require_admin()
            if not ok:
                return
            uni_id = match_uni.group(1)
            campus_service.delete_university(uni_id)
            self.send_json({"success": True})
            return

        # Admin: Delete Campus Paper
        match_paper = re.match(r'^/api/admin/campus/papers/([a-zA-Z0-9_\-]+)$', path)
        if match_paper:
            user, ok = self.require_admin()
            if not ok:
                return
            paper_id = match_paper.group(1)
            campus_service.delete_paper(paper_id)
            self.send_json({"success": True})
            return

        # Admin: Delete Gallery Poster
        match_poster_del = re.match(r'^/api/admin/gallery/posters/([a-zA-Z0-9_\-]+)$', path)
        if match_poster_del:
            user, ok = self.require_admin()
            if not ok:
                return
            poster_id = match_poster_del.group(1)
            gallery_service.delete_poster(poster_id)
            self.send_json({"success": True})
            return

        # Admin: Delete Previous Event
        match_pe_del = re.match(r'^/api/admin/gallery/previous-events/([a-zA-Z0-9_\-]+)$', path)
        if match_pe_del:
            user, ok = self.require_admin()
            if not ok:
                return
            event_id = match_pe_del.group(1)
            gallery_service.delete_previous_event(event_id)
            self.send_json({"success": True})
            return

        # User / Admin: Delete Community Project
        match_cp_del = re.match(r'^/api/community/projects/([a-zA-Z0-9_\-]+)$', path)
        if match_cp_del:
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Unauthorized"}, 401)
                return
            proj_id = match_cp_del.group(1)
            self.handle_community_project_delete(proj_id, user)
            return

        # User / Admin: Delete Community Comment
        match_comm_del = re.match(r'^/api/community/comments/([a-zA-Z0-9_\-]+)$', path)
        if match_comm_del:
            user = self.get_current_user()
            if not user:
                self.send_json({"error": "Unauthorized"}, 401)
                return
            comm_id = match_comm_del.group(1)
            self.handle_community_project_comment_delete(comm_id, user)
            return

        self.send_json({"error": "Not Found"}, 404)

    # ------------------ Endpoint Handlers ------------------

    def handle_send_otp(self):
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
        if is_rate_limited(client_ip, limit=10, window_sec=60):
            self.send_json({"success": False, "error": "Too many OTP requests. Please wait a minute before retrying."}, 429)
            return

        body = self.read_json_body()
        email = body.get('email', '').strip().lower()
        raw_purpose = body.get('purpose', 'Sign Up Verification')
        purpose = normalize_purpose(raw_purpose)

        if not email or '@' not in email:
            self.send_json({"success": False, "error": "A valid email address is required."}, 400)
            return

        # If for signup, ensure user does not already exist
        if 'sign' in purpose.lower():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                conn.close()
                self.send_json({"success": False, "error": "An account with this email already exists. Please log in."}, 409)
                return
            conn.close()

        # If for password reset, ensure user exists
        if 'reset' in purpose.lower() or 'password' in purpose.lower():
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
            conn.close()
            if not user:
                self.send_json({"success": False, "error": "No account found with this email address. Please check your email or sign up."}, 404)
                return

        res = generate_and_store_otp(email, purpose=purpose)
        if not res.get("success", False) and res.get("smtp_error"):
            self.send_json({
                "success": False,
                "error": res.get("smtp_error")
            }, 400)
            return

        self.send_json({
            "success": True,
            "message": f"✓ 6-digit verification code dispatched to {email}",
            "email": email,
            "dev_otp": res.get("dev_otp")
        })

    def handle_reset_password(self):
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
        if is_rate_limited(client_ip, limit=12, window_sec=60):
            self.send_json({"success": False, "error": "Too many password reset attempts. Please wait a minute."}, 429)
            return

        body = self.read_json_body()
        email = body.get('email', '').strip().lower()
        otp = body.get('otp', '').strip()
        new_password = body.get('password', '')
        confirm_password = body.get('confirm_password', '')

        if not email or '@' not in email:
            self.send_json({"success": False, "error": "A valid email address is required."}, 400)
            return

        if not otp:
            self.send_json({"success": False, "error": "6-digit OTP verification code is required."}, 400)
            return

        if not new_password:
            self.send_json({"success": False, "error": "New password is required."}, 400)
            return

        if len(new_password) < 6:
            self.send_json({"success": False, "error": "Password must be at least 6 characters."}, 400)
            return

        if confirm_password and new_password != confirm_password:
            self.send_json({"success": False, "error": "Passwords do not match."}, 400)
            return

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            self.send_json({"success": False, "error": "No account found with this email address."}, 404)
            return

        # Verify OTP
        if not verify_otp(email, otp, purpose="Password Reset"):
            self.send_json({"success": False, "error": "Invalid or expired verification code. Please check your email or request a new code."}, 400)
            return

        ok = reset_user_password(email, new_password)
        if not ok:
            self.send_json({"success": False, "error": "Could not reset password. Please try again."}, 500)
            return

        self.send_json({
            "success": True,
            "message": "Password reset successfully! You can now log in with your new password."
        })

    def handle_register(self):
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"
        if is_rate_limited(client_ip, limit=12, window_sec=60):
            self.send_json({"success": False, "error": "Too many registration attempts. Please wait a minute."}, 429)
            return

        body = self.read_json_body()
        email = body.get('email', '').strip().lower()
        password = body.get('password', '')
        otp = body.get('otp', '').strip()
        name = body.get('name') or body.get('full_name') or email.split('@')[0]
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        if not email or not password:
            self.send_json({"success": False, "error": "Email and password are required."}, 400)
            return

        if len(password) < 6:
            self.send_json({"success": False, "error": "Password must be at least 6 characters."}, 400)
            return

        if not otp:
            self.send_json({"success": False, "error": "Email verification code (OTP) is required to sign up."}, 400)
            return

        # Verify OTP
        if not verify_otp(email, otp, purpose="Sign Up Verification"):
            self.send_json({"success": False, "error": "Invalid or expired verification code. Please check your email or request a new code."}, 400)
            return

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            conn.close()
            self.send_json({"success": False, "error": "An account with this email already exists. Please log in."}, 409)
            return
        conn.close()

        # Regular signup is ALWAYS role='user' - member cannot be admin
        user_info = create_or_update_user(email, password, role='user', name=name)
        
        college = body.get('college_name')
        grad_year = body.get('grad_year')
        github = body.get('github_handle')
        leetcode = body.get('leetcode_handle')
        if any([college, grad_year, github, leetcode]):
            update_user_profile(user_info["id"], {
                "college_name": college,
                "grad_year": grad_year,
                "github_handle": github,
                "leetcode_handle": leetcode
            })

        token = create_session(user_info["id"], user_info["role"], ip_address=client_ip)
        cookie = cookies.SimpleCookie()
        cookie['devengers_session'] = token
        cookie['devengers_session']['path'] = '/'
        cookie['devengers_session']['httponly'] = True
        cookie['devengers_session']['samesite'] = 'Lax'
        cookie['devengers_session']['max-age'] = 604800

        self.send_json({
            "success": True,
            "message": "Account created successfully!",
            "user": {
                "id": user_info["id"],
                "email": user_info["email"],
                "name": name,
                "role": user_info["role"]
            },
            "token": token,
            "redirect": "profile.html"
        }, 201, extra_headers={"Set-Cookie": cookie['devengers_session'].OutputString()})

    def handle_login(self):
        body = self.read_json_body()
        email = body.get('email', '').strip().lower()
        password = body.get('password', '')
        otp = body.get('otp', '').strip() or None
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        if is_rate_limited(client_ip, limit=15, window_sec=60):
            self.send_json({"success": False, "error": "Too many login attempts. Please wait 1 minute before retrying."}, 429)
            return

        if not email or not password:
            self.send_json({"success": False, "error": "Email and password are required."}, 400)
            return

        user, err = authenticate(email, password, client_ip=client_ip, otp=otp)
        
        if err:
            if err.startswith("REQUIRES_ADMIN_OTP"):
                dev_otp = err.split(":", 1)[1] if ":" in err else None
                self.send_json({
                    "success": False,
                    "requires_otp": True,
                    "email": email,
                    "dev_otp": dev_otp,
                    "message": "Admin Security Check: 6-digit 2FA passcode sent to event@devengers.org"
                }, 200)
                return

            self.send_json({"success": False, "error": err or "Invalid credentials."}, 401)
            return

        token = create_session(user["id"], user["role"], ip_address=client_ip)
        cookie = cookies.SimpleCookie()
        cookie['devengers_session'] = token
        cookie['devengers_session']['path'] = '/'
        cookie['devengers_session']['httponly'] = True
        cookie['devengers_session']['samesite'] = 'Lax'
        cookie['devengers_session']['max-age'] = 604800 # 7 days

        # Determine redirect destination based on role
        redirect_url = "admin-events.html" if user["role"] == "admin" else "profile.html"

        self.send_json({
            "success": True,
            "user": user,
            "token": token,
            "redirect": redirect_url
        }, 200, extra_headers={"Set-Cookie": cookie['devengers_session'].OutputString()})

    def handle_google_auth(self):
        body = self.read_json_body()
        credential = body.get('credential', '').strip()
        client_ip = self.client_address[0] if self.client_address else "127.0.0.1"

        email = body.get('email', '').strip().lower()
        name = body.get('name') or body.get('full_name')
        picture = body.get('picture') or body.get('avatar_url')
        google_id = body.get('sub') or body.get('google_id')

        # If Google GIS ID Token JWT is sent
        if credential:
            try:
                parts = credential.split('.')
                if len(parts) >= 2:
                    payload_b64 = parts[1]
                    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                    payload_bytes = base64.urlsafe_b64decode(payload_b64)
                    token_data = json.loads(payload_bytes.decode('utf-8'))
                    email = token_data.get('email', email).strip().lower()
                    name = token_data.get('name', name)
                    picture = token_data.get('picture', picture)
                    google_id = token_data.get('sub', google_id)
            except Exception as e:
                print(f"[GOOGLE AUTH] Failed to parse credential JWT: {e}")

        if not email or '@' not in email:
            self.send_json({"success": False, "error": "A valid Google account email is required."}, 400)
            return

        res, err = authenticate_or_create_google_user(email, name=name, picture=picture, google_id=google_id)

        if err:
            self.send_json({"success": False, "error": err}, 400)
            return

        if isinstance(res, dict) and res.get("requires_otp"):
            self.send_json({
                "success": False,
                "requires_otp": True,
                "email": email,
                "message": res.get("message", "Admin 2FA Security: 6-digit passcode sent to event@devengers.org")
            }, 200)
            return

        user = res
        token = create_session(user["id"], user["role"], ip_address=client_ip)
        cookie = cookies.SimpleCookie()
        cookie['devengers_session'] = token
        cookie['devengers_session']['path'] = '/'
        cookie['devengers_session']['httponly'] = True
        cookie['devengers_session']['samesite'] = 'Lax'
        cookie['devengers_session']['max-age'] = 604800  # 7 days

        redirect_url = "admin-events.html" if user["role"] == "admin" else "profile.html"

        self.send_json({
            "success": True,
            "user": user,
            "token": token,
            "redirect": redirect_url
        }, 200, extra_headers={"Set-Cookie": cookie['devengers_session'].OutputString()})

    def handle_logout(self):
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            c = cookies.SimpleCookie()
            try:
                c.load(cookie_header)
                if 'devengers_session' in c:
                    delete_session(c['devengers_session'].value)
            except Exception:
                pass

        cookie = cookies.SimpleCookie()
        cookie['devengers_session'] = ''
        cookie['devengers_session']['path'] = '/'
        cookie['devengers_session']['httponly'] = True
        cookie['devengers_session']['max-age'] = 0

        self.send_json({"success": True}, 200, extra_headers={"Set-Cookie": cookie['devengers_session'].OutputString()})

    def handle_public_events(self, query):
        category = query.get('category', [''])[0].strip()
        search = query.get('search', [''])[0].strip()
        job_type = query.get('job_type', [''])[0].strip()
        experience_level = query.get('experience_level', [''])[0].strip()
        location = query.get('location', [''])[0].strip()

        conn = get_connection()
        cursor = conn.cursor()

        sql = """
            SELECT * FROM events
            WHERE status = 'Published'
        """
        params = []

        # Strictly exclude jobs and internships whose registration deadline has passed
        now_iso = datetime.now(timezone.utc).isoformat()
        sql += " AND (category NOT IN ('Jobs', 'Internships') OR reg_deadline IS NULL OR reg_deadline = '' OR reg_deadline >= ?)"
        params.append(now_iso)

        if category and category.lower() not in ('all', 'all events', ''):
            sql += " AND category = ?"
            params.append(category)

        if job_type:
            sql += " AND job_type LIKE ?"
            params.append(f"%{job_type}%")

        if experience_level:
            sql += " AND experience_level LIKE ?"
            params.append(f"%{experience_level}%")

        if location:
            sql += " AND location LIKE ?"
            params.append(f"%{location}%")

        if search:
            sql += " AND (title LIKE ? OR short_description LIKE ? OR organizer LIKE ? OR location LIKE ? OR tags LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term, term])

        # Default order: nearest upcoming deadline first, then newest
        sql += " ORDER BY reg_deadline ASC, created_at DESC"

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        events = [dict(r) for r in rows]
        conn.close()

        self.send_json({
            "success": True,
            "count": len(events),
            "events": events
        })

    def handle_public_single_event(self, event_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ? AND status = 'Published'", (event_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            self.send_json({"error": "Event not found"}, 404)
            return
        self.send_json({"success": True, "event": dict(row)})

    def handle_admin_events(self, query):
        category = query.get('category', [''])[0].strip()
        status = query.get('status', [''])[0].strip()
        search = query.get('search', [''])[0].strip()

        conn = get_connection()
        cursor = conn.cursor()

        # Gather summary statistics for dashboard metrics
        cursor.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Published' THEN 1 ELSE 0 END) AS published,
                SUM(CASE WHEN status = 'Draft' THEN 1 ELSE 0 END) AS drafts,
                SUM(CASE WHEN status = 'Unpublished' THEN 1 ELSE 0 END) AS unpublished,
                SUM(CASE WHEN status = 'Archived' THEN 1 ELSE 0 END) AS archived
            FROM events
        """)
        stats_row = cursor.fetchone()
        stats = {
            "total": stats_row["total"] or 0,
            "published": stats_row["published"] or 0,
            "drafts": stats_row["drafts"] or 0,
            "unpublished": stats_row["unpublished"] or 0,
            "archived": stats_row["archived"] or 0
        }

        sql = "SELECT * FROM events WHERE 1=1"
        params = []

        if category and category.lower() not in ('all', 'all events', ''):
            sql += " AND category = ?"
            params.append(category)

        if status and status.lower() not in ('all', ''):
            sql += " AND status = ?"
            params.append(status)

        if search:
            sql += " AND (title LIKE ? OR short_description LIKE ? OR organizer LIKE ? OR tags LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term])

        sql += " ORDER BY updated_at DESC"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        events = [dict(r) for r in rows]
        conn.close()

        self.send_json({
            "success": True,
            "stats": stats,
            "count": len(events),
            "events": events
        })

    def handle_admin_single_event(self, event_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            self.send_json({"error": "Event not found"}, 404)
            return
        self.send_json({"success": True, "event": dict(row)})

    def handle_create_event(self, admin_user):
        body = self.read_json_body()

        title = body.get('title', '').strip()
        short_desc = body.get('short_description', '').strip()
        full_desc = body.get('full_description', '').strip()
        category = body.get('category', '').strip()
        organizer = body.get('organizer', '').strip() or "Devengers Tech Community"
        thumbnail = body.get('thumbnail', '').strip()
        reg_open = body.get('reg_open_date') or None
        reg_deadline = body.get('reg_deadline', '').strip()
        event_start = body.get('event_start_date') or None
        event_end = body.get('event_end_date') or None
        prize_amt = body.get('prize_amount')
        prize_curr = body.get('prize_currency', 'INR').strip()
        prize_desc = body.get('prize_description', '').strip()
        reg_fee = float(body.get('reg_fee', 0.0) or 0.0)
        dest_url = body.get('destination_url', '').strip()
        action_label = body.get('action_label', 'Register Now').strip() or "Register Now"
        status = body.get('status', 'Draft').strip()
        location = body.get('location', '').strip() or "(Remote)"
        job_type = body.get('job_type', '').strip() or "Full Time"
        experience_level = body.get('experience_level', '').strip() or "Entry Level"
        org_logo = body.get('org_logo', '').strip() or "Assest/devengers-logo.png"
        banner_fit = body.get('banner_fit', 'cover').strip() or "cover"
        tags = body.get('tags', '').strip()

        # Validation
        errors = []
        if not title:
            errors.append("Title is required.")
        if not short_desc:
            errors.append("Short description is required.")
        if category not in ALLOWED_CATEGORIES:
            errors.append(f"Category must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}")
        if not reg_deadline:
            errors.append("Registration deadline is required.")
        if status not in ALLOWED_STATUSES:
            status = 'Draft'

        # If publishing, require thumbnail and valid safe destination URL
        if status == 'Published':
            if not thumbnail:
                errors.append("Thumbnail is required before publishing an event.")
            if not dest_url:
                errors.append("Destination / Registration URL is required before publishing an event.")
            elif not is_safe_url(dest_url):
                errors.append("Destination URL must begin with http:// or https:// (unsafe schemes are rejected).")

        # Validate date ranges
        if reg_open and reg_deadline and reg_deadline < reg_open:
            errors.append("Registration closing deadline cannot be earlier than opening date.")
        if event_start and event_end and event_end < event_start:
            errors.append("Event end time cannot be earlier than start time.")

        if errors:
            self.send_json({"success": False, "errors": errors}, 400)
            return

        event_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (
                id, title, short_description, full_description, category, organizer,
                thumbnail, reg_open_date, reg_deadline, event_start_date, event_end_date,
                prize_amount, prize_currency, prize_description, reg_fee,
                destination_url, action_label, status, created_by, created_at, updated_at,
                location, job_type, experience_level, org_logo, banner_fit, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, title, short_desc, full_desc, category, organizer,
            thumbnail or "Assest/devengers-logo.png", reg_open, reg_deadline,
            event_start, event_end, prize_amt, prize_curr, prize_desc, reg_fee,
            dest_url, action_label, status, admin_user["id"], now_iso, now_iso,
            location, job_type, experience_level, org_logo, banner_fit, tags
        ))
        conn.commit()

        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        created = dict(cursor.fetchone())
        conn.close()

        self.send_json({"success": True, "event": created}, 201)

    def handle_update_event(self, event_id, admin_user):
        body = self.read_json_body()

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            self.send_json({"error": "Event not found"}, 404)
            return

        title = body.get('title', existing['title']).strip()
        short_desc = body.get('short_description', existing['short_description']).strip()
        full_desc = body.get('full_description', existing['full_description'])
        category = body.get('category', existing['category']).strip()
        organizer = body.get('organizer', existing['organizer']).strip()
        thumbnail = body.get('thumbnail', existing['thumbnail']).strip()
        reg_open = body.get('reg_open_date', existing['reg_open_date'])
        reg_deadline = body.get('reg_deadline', existing['reg_deadline']).strip()
        event_start = body.get('event_start_date', existing['event_start_date'])
        event_end = body.get('event_end_date', existing['event_end_date'])
        prize_amt = body.get('prize_amount', existing['prize_amount'])
        prize_curr = body.get('prize_currency', existing['prize_currency'])
        prize_desc = body.get('prize_description', existing['prize_description'])
        reg_fee = float(body.get('reg_fee', existing['reg_fee']) or 0.0)
        dest_url = body.get('destination_url', existing['destination_url']).strip()
        action_label = body.get('action_label', existing['action_label']).strip()
        status = body.get('status', existing['status']).strip()
        existing_keys = existing.keys()
        location = body.get('location', existing['location'] if 'location' in existing_keys else '(Remote)')
        job_type = body.get('job_type', existing['job_type'] if 'job_type' in existing_keys else 'Full Time')
        experience_level = body.get('experience_level', existing['experience_level'] if 'experience_level' in existing_keys else 'Entry Level')
        org_logo = body.get('org_logo', existing['org_logo'] if 'org_logo' in existing_keys else 'Assest/devengers-logo.png')
        banner_fit = body.get('banner_fit', existing['banner_fit'] if 'banner_fit' in existing_keys else 'cover')
        tags = body.get('tags', existing['tags'] if 'tags' in existing_keys else '').strip()

        # Validation
        errors = []
        if not title:
            errors.append("Title is required.")
        if not short_desc:
            errors.append("Short description is required.")
        if category not in ALLOWED_CATEGORIES:
            errors.append(f"Category must be one of: {', '.join(sorted(ALLOWED_CATEGORIES))}")
        if not reg_deadline:
            errors.append("Registration deadline is required.")
        if status not in ALLOWED_STATUSES:
            status = existing['status']

        if status == 'Published':
            if not thumbnail:
                errors.append("Thumbnail is required before publishing.")
            if not dest_url:
                errors.append("Destination URL is required before publishing.")
            elif not is_safe_url(dest_url):
                errors.append("Destination URL must begin with http:// or https://")

        if reg_open and reg_deadline and reg_deadline < reg_open:
            errors.append("Registration deadline cannot be earlier than opening date.")
        if event_start and event_end and event_end < event_start:
            errors.append("Event end time cannot be earlier than start time.")

        if errors:
            conn.close()
            self.send_json({"success": False, "errors": errors}, 400)
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        archived_at = now_iso if status == 'Archived' else (None if existing['status'] == 'Archived' else existing['archived_at'])

        cursor.execute("""
            UPDATE events SET
                title = ?, short_description = ?, full_description = ?, category = ?,
                organizer = ?, thumbnail = ?, reg_open_date = ?, reg_deadline = ?,
                event_start_date = ?, event_end_date = ?, prize_amount = ?,
                prize_currency = ?, prize_description = ?, reg_fee = ?,
                destination_url = ?, action_label = ?, status = ?,
                updated_at = ?, archived_at = ?,
                location = ?, job_type = ?, experience_level = ?,
                org_logo = ?, banner_fit = ?, tags = ?
            WHERE id = ?
        """, (
            title, short_desc, full_desc, category, organizer, thumbnail,
            reg_open, reg_deadline, event_start, event_end, prize_amt,
            prize_curr, prize_desc, reg_fee, dest_url, action_label, status,
            now_iso, archived_at,
            location, job_type, experience_level,
            org_logo, banner_fit, tags,
            event_id
        ))
        conn.commit()

        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        updated = dict(cursor.fetchone())
        conn.close()

        self.send_json({"success": True, "event": updated})

    def handle_update_event_status(self, event_id):
        body = self.read_json_body()
        new_status = body.get('status', '').strip()
        if new_status not in ALLOWED_STATUSES:
            self.send_json({"error": f"Invalid status: {new_status}"}, 400)
            return

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        existing = cursor.fetchone()
        if not existing:
            conn.close()
            self.send_json({"error": "Event not found"}, 404)
            return

        # Check required fields if publishing
        if new_status == 'Published':
            if not existing['thumbnail']:
                conn.close()
                self.send_json({"error": "Cannot publish: Thumbnail image is required."}, 400)
                return
            if not existing['destination_url'] or not is_safe_url(existing['destination_url']):
                conn.close()
                self.send_json({"error": "Cannot publish: Valid HTTP/HTTPS destination URL is required."}, 400)
                return

        now_iso = datetime.now(timezone.utc).isoformat()
        archived_at = now_iso if new_status == 'Archived' else None

        cursor.execute("""
            UPDATE events SET status = ?, updated_at = ?, archived_at = ?
            WHERE id = ?
        """, (new_status, now_iso, archived_at, event_id))
        conn.commit()
        conn.close()

        self.send_json({"success": True, "id": event_id, "status": new_status})

    def handle_delete_event(self, event_id):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted_count == 0:
            self.send_json({"error": "Event not found"}, 404)
            return

        self.send_json({"success": True, "id": event_id})

    def handle_image_upload(self):
        """Processes multipart form-data image upload with server-side validation."""
        content_type = self.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            self.send_json({"error": "Content-Type must be multipart/form-data"}, 400)
            return

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0 or content_length > 5 * 1024 * 1024: # 5MB limit
            self.send_json({"error": "File size must be greater than 0 and less than 5MB"}, 400)
            return

        boundary = content_type.split("boundary=")[-1].strip().encode('utf-8')
        raw_body = self.rfile.read(content_length)

        # Parse multipart body
        parts = raw_body.split(b'--' + boundary)
        file_bytes = None
        orig_filename = ""

        for part in parts:
            if b'filename="' in part:
                headers_part, _, body_part = part.partition(b'\r\n\r\n')
                # Extract filename
                match = re.search(r'filename="([^"]+)"', headers_part.decode('latin1', errors='ignore'))
                if match:
                    orig_filename = match.group(1)
                # Strip trailing CRLF
                if body_part.endswith(b'\r\n'):
                    body_part = body_part[:-2]
                file_bytes = body_part
                break

        if not file_bytes:
            self.send_json({"error": "No file payload found in form-data"}, 400)
            return

        # Validate actual magic bytes (never trust extension)
        detected_ext = validate_image_magic(file_bytes)
        if not detected_ext or detected_ext not in ('png', 'jpg', 'webp', 'gif'):
            self.send_json({"error": "Invalid image format. Only JPEG, PNG, and WebP images are permitted."}, 400)
            return

        # Generate safe filename and save to uploads folder
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        safe_name = f"evt_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}.{detected_ext}"
        target_path = os.path.join(UPLOADS_DIR, safe_name)

        with open(target_path, 'wb') as f:
            f.write(file_bytes)

        rel_url = f"Assest/uploads/{safe_name}"
        self.send_json({
            "success": True,
            "url": rel_url,
            "filename": safe_name,
            "size": len(file_bytes)
        })

    def handle_sync_status(self):
        from db import get_setting, get_recent_sync_logs
        self.send_json({
            "success": True,
            "schedule": "Daily at 11:59 PM IST",
            "auto_sync_enabled": get_setting("auto_sync_enabled", "true") == "true",
            "last_sync_time": get_setting("last_sync_time", ""),
            "last_sync_count": int(get_setting("last_sync_count", "0") or 0),
            "last_sync_status": get_setting("last_sync_status", "idle"),
            "recent_logs": get_recent_sync_logs(limit=5)
        })

    def handle_trigger_sync(self):
        from job_sync_service import run_job_sync
        res = run_job_sync(source_trigger='Manual Admin Sync')
        self.send_json({"success": True, "result": res})

    def handle_flash_fetch(self):
        body = self.read_json_body()
        url = body.get('url', '').strip()
        category = body.get('category', 'Hackathons').strip()

        if not url:
            self.send_json({"success": False, "error": "Please provide an event link (e.g. Unstop, Devfolio, MLH)."}, 400)
            return

        if not is_safe_url(url):
            self.send_json({"success": False, "error": "Destination link must start with http:// or https://"}, 400)
            return

        if category not in ('Hackathons', 'Quizzes'):
            category = 'Hackathons'

        try:
            from flash_event_service import extract_flash_event
            data = extract_flash_event(url, selected_category=category, base_dir=DIRECTORY)
            self.send_json({"success": True, "event": data})
        except Exception as e:
            self.send_json({"success": False, "error": f"Failed to auto-fetch details from link: {str(e)}"}, 500)

    # ------------------ Learn & Courses Handlers ------------------

    def handle_public_courses(self, query):
        cat = query.get('category', [None])[0]
        ctype = query.get('type', [None])[0]
        search = query.get('search', [None])[0]

        courses = get_courses(category=cat, course_type=ctype, status='Published', search=search)
        settings = get_learn_settings()
        self.send_json({
            "success": True,
            "courses": courses,
            "total": len(courses),
            "coming_soon": settings
        })

    def handle_get_pyqs(self, query):
        catalog_path = os.path.join(DIRECTORY, "Assest", "pyqs", "pyqs_catalog.json")
        if not os.path.exists(catalog_path):
            self.send_json({"success": False, "error": "PYQs catalog not built yet."}, 404)
            return

        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.send_json({"success": False, "error": f"Failed reading catalog: {e}"}, 500)
            return

        uni = query.get('university', [None])[0]
        year = query.get('year', [None])[0]
        sem = query.get('semester', [None])[0]
        search = query.get('search', [None])[0]
        exam_yr = query.get('exam_year', [None])[0]

        papers = data.get("papers", [])
        if uni and uni.lower() != 'all':
            papers = [p for p in papers if p["university_id"].lower() == uni.lower()]
        if year and year.lower() != 'all':
            try:
                yr_int = int(year)
                papers = [p for p in papers if p["year"] == yr_int]
            except ValueError:
                pass
        if sem and sem.lower() != 'all':
            try:
                sem_int = int(sem)
                papers = [p for p in papers if p["semester"] == sem_int]
            except ValueError:
                pass
        if exam_yr and exam_yr.lower() != 'all':
            papers = [p for p in papers if p["exam_year"] == exam_yr]
        if search:
            s = search.strip().lower()
            papers = [p for p in papers if s in p["subject_title"].lower() or s in p["subject_code"].lower() or s in p["university_name"].lower()]

        self.send_json({
            "success": True,
            "universities": data.get("universities", []),
            "curriculum": data.get("curriculum", {}),
            "papers": papers,
            "total": len(papers),
            "total_catalog": len(data.get("papers", []))
        })

    def handle_public_single_course(self, course_id):
        c = get_course(course_id)
        if not c or c.get('status') != 'Published':
            self.send_json({"error": "Course not found"}, 404)
            return
        self.send_json({"success": True, "course": c})

    def handle_admin_courses(self, query):
        cat = query.get('category', [None])[0]
        ctype = query.get('type', [None])[0]
        status = query.get('status', [None])[0]
        search = query.get('search', [None])[0]

        courses = get_courses(category=cat, course_type=ctype, status=status, search=search)
        all_courses = get_courses(status=None)
        
        counts = {
            "total": len(all_courses),
            "free": sum(1 for c in all_courses if c.get('type') == 'free'),
            "paid": sum(1 for c in all_courses if c.get('type') == 'paid'),
            "doc": sum(1 for c in all_courses if c.get('type') in ('doc', 'pdf')),
            "published": sum(1 for c in all_courses if c.get('status') == 'Published'),
            "draft": sum(1 for c in all_courses if c.get('status') == 'Draft')
        }
        settings = get_learn_settings()
        self.send_json({
            "success": True,
            "courses": courses,
            "stats": counts,
            "settings": settings
        })

    def handle_admin_single_course(self, course_id):
        c = get_course(course_id)
        if not c:
            self.send_json({"error": "Course not found"}, 404)
            return
        self.send_json({"success": True, "course": c})

    def handle_create_course(self):
        body = self.read_json_body()
        title = body.get('title', '').strip()
        if not title:
            self.send_json({"error": "Course title is required."}, 400)
            return
        dest_url = body.get('destination_url', '').strip()
        if not dest_url or not is_safe_url(dest_url):
            self.send_json({"error": "Valid course destination URL (http/https) is required."}, 400)
            return
        doc_url = body.get('doc_url', '').strip()
        if doc_url and not is_safe_url(doc_url):
            self.send_json({"error": "Documentation/PDF link must start with http:// or https://"}, 400)
            return

        created = create_course(body)
        self.send_json({"success": True, "course": created}, 201)

    def handle_update_course(self, course_id):
        existing = get_course(course_id)
        if not existing:
            self.send_json({"error": "Course not found"}, 404)
            return
        body = self.read_json_body()
        dest_url = body.get('destination_url', '').strip()
        if dest_url and not is_safe_url(dest_url):
            self.send_json({"error": "Valid course destination URL (http/https) is required."}, 400)
            return
        doc_url = body.get('doc_url', '').strip()
        if doc_url and not is_safe_url(doc_url):
            self.send_json({"error": "Documentation/PDF link must start with http:// or https://"}, 400)
            return

        updated = update_course(course_id, body)
        self.send_json({"success": True, "course": updated})

    def handle_update_course_status(self, course_id):
        existing = get_course(course_id)
        if not existing:
            self.send_json({"error": "Course not found"}, 404)
            return
        body = self.read_json_body()
        new_status = body.get('status')
        if new_status not in ('Draft', 'Published', 'Unpublished', 'Archived'):
            self.send_json({"error": "Invalid status value"}, 400)
            return
        existing['status'] = new_status
        updated = update_course(course_id, existing)
        self.send_json({"success": True, "course": updated})

    def handle_delete_course(self, course_id):
        existing = get_course(course_id)
        if not existing:
            self.send_json({"error": "Course not found"}, 404)
            return
        delete_course(course_id)
        self.send_json({"success": True, "message": "Course deleted successfully"})

    def handle_get_learn_settings(self):
        settings = get_learn_settings()
        self.send_json({"success": True, "settings": settings})

    def handle_update_learn_settings(self):
        body = self.read_json_body()
        updated = update_learn_settings(body)
        self.send_json({"success": True, "settings": updated})

    def handle_reseed_courses(self):
        seed_starter_courses_if_empty(force_reseed=True)
        self.send_json({"success": True, "message": "Reseeded starter courses with general non-biased platforms"})

    # ------------------ User Profile, Progress & Application Handlers ------------------

    def handle_get_user_profile(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Unauthorized: Please log in to view your profile."}, 401)
            return
        profile = get_user_full_profile(user["id"])
        if not profile:
            self.send_json({"error": "User profile not found"}, 404)
            return
        self.send_json({"success": True, "profile": profile})

    def handle_update_user_profile(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Unauthorized"}, 401)
            return
        body = self.read_json_body()
        updated = update_user_profile(user["id"], body)
        self.send_json({"success": True, "profile": updated})

    def handle_user_daily_checkin(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Unauthorized"}, 401)
            return
        streak = log_daily_user_checkin(user["id"])
        profile = get_user_full_profile(user["id"])
        self.send_json({
            "success": True,
            "streak": streak,
            "profile": profile,
            "message": f"🔥 Checked in! Current streak: {streak} Day{'s' if streak != 1 else ''}"
        })

    def handle_user_media_upload(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Unauthorized"}, 401)
            return

        content_type = self.headers.get('Content-Type', '')
        file_bytes = None
        media_type = "avatar"

        if content_type.startswith('application/json'):
            body = self.read_json_body()
            media_type = body.get("media_type", "avatar")
            b64_str = body.get("image_base64") or body.get("image_data") or ""
            if "base64," in b64_str:
                b64_str = b64_str.split("base64,")[1]
            try:
                file_bytes = base64.b64decode(b64_str)
            except Exception as e:
                self.send_json({"error": f"Base64 decode failed: {e}"}, 400)
                return
        elif content_type.startswith('multipart/form-data'):
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > 10 * 1024 * 1024:
                self.send_json({"error": "File size must be greater than 0 and less than 10MB"}, 400)
                return

            boundary = content_type.split("boundary=")[-1].strip().encode('utf-8')
            raw_body = self.rfile.read(content_length)
            parts = raw_body.split(b'--' + boundary)

            for part in parts:
                if b'name="media_type"' in part:
                    _, _, val = part.partition(b'\r\n\r\n')
                    media_type = val.strip().decode('utf-8', errors='ignore') or "avatar"
                if b'filename="' in part:
                    headers_part, _, body_part = part.partition(b'\r\n\r\n')
                    if body_part.endswith(b'\r\n'):
                        body_part = body_part[:-2]
                    file_bytes = body_part
                    break
        else:
            self.send_json({"error": "Unsupported Content-Type"}, 400)
            return

        if not file_bytes:
            self.send_json({"error": "No image data provided"}, 400)
            return

        detected_ext = validate_image_magic(file_bytes) or 'png'
        if detected_ext not in ('png', 'jpg', 'webp', 'gif'):
            detected_ext = 'png'

        os.makedirs(UPLOADS_DIR, exist_ok=True)
        safe_name = f"usr_{media_type}_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}.{detected_ext}"
        target_path = os.path.join(UPLOADS_DIR, safe_name)

        with open(target_path, 'wb') as f:
            f.write(file_bytes)

        rel_url = f"Assest/uploads/{safe_name}"
        if media_type == "avatar":
            update_user_profile(user["id"], {"avatar_url": rel_url})

        self.send_json({
            "success": True,
            "url": rel_url,
            "filename": safe_name,
            "media_type": media_type
        })

    def handle_get_user_course_progress(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"success": True, "completed_course_ids": []})
            return
        ids = get_user_completed_course_ids(user["id"])
        self.send_json({"success": True, "completed_course_ids": ids})

    def handle_toggle_course_progress(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Please log in to track course completion on your profile."}, 401)
            return
        body = self.read_json_body()
        course_id = body.get('course_id')
        if not course_id:
            self.send_json({"error": "course_id is required"}, 400)
            return
        completed = toggle_user_course_progress(user["id"], course_id)
        ids = get_user_completed_course_ids(user["id"])
        self.send_json({
            "success": True,
            "course_id": course_id,
            "completed": completed,
            "completed_course_ids": ids
        })

    def handle_get_user_applications(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"success": True, "applied_event_ids": []})
            return
        ids = get_user_applied_event_ids(user["id"])
        self.send_json({"success": True, "applied_event_ids": ids})

    def handle_toggle_application(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Please log in to track applications on your profile."}, 401)
            return
        body = self.read_json_body()
        event_id = body.get('event_id')
        if not event_id:
            self.send_json({"error": "event_id is required"}, 400)
            return
        applied = toggle_user_application(user["id"], event_id)
        ids = get_user_applied_event_ids(user["id"])
        self.send_json({
            "success": True,
            "event_id": event_id,
            "applied": applied,
            "applied_event_ids": ids
        })

    def handle_log_study_activity(self):
        user = self.get_current_user()
        if not user:
            self.send_json({"error": "Unauthorized: Please log in."}, 401)
            return
        body = self.read_json_body()
        count = int(body.get('questions_count') or body.get('points') or 1)
        topic = body.get('topic', '').strip()
        updated_profile = log_user_questions_solved(user["id"], count=count, topic=topic)
        self.send_json({"success": True, "profile": updated_profile, "points_added": count})

    # --- Campus & PYQs Admin Handlers ---

    def handle_admin_campus_papers(self, query):
        catalog = campus_service.get_catalog_data()
        papers = catalog.get("papers", [])

        uni = query.get('university', [None])[0]
        year = query.get('year', [None])[0]
        sem = query.get('semester', [None])[0]
        exam_yr = query.get('exam_year', [None])[0]
        search = query.get('search', [None])[0]

        if uni and uni.lower() != 'all':
            papers = [p for p in papers if p.get("university_id", "").lower() == uni.lower()]
        if year and year.lower() != 'all':
            try:
                yr_int = int(year)
                papers = [p for p in papers if p.get("year") == yr_int]
            except ValueError:
                pass
        if sem and sem.lower() != 'all':
            try:
                sem_int = int(sem)
                papers = [p for p in papers if p.get("semester") == sem_int]
            except ValueError:
                pass
        if exam_yr and exam_yr.lower() != 'all':
            papers = [p for p in papers if p.get("exam_year") == exam_yr]
        if search:
            s = search.strip().lower()
            papers = [p for p in papers if s in p.get("subject_title", "").lower() or s in p.get("subject_code", "").lower() or s in p.get("university_short", "").lower()]

        self.send_json({
            "success": True,
            "papers": papers,
            "total": len(papers),
            "universities": catalog.get("universities", [])
        })

    def handle_save_university(self):
        body = self.read_json_body()
        if not body or not body.get("name") or not body.get("short_name"):
            self.send_json({"error": "University name and short_name are required."}, 400)
            return
        saved = campus_service.save_university(body)
        self.send_json({"success": True, "university": saved})

    def handle_save_curriculum(self):
        body = self.read_json_body()
        sem = body.get("semester")
        if not sem:
            self.send_json({"error": "Semester number (1-8) is required."}, 400)
            return
        saved = campus_service.save_curriculum(sem, body)
        self.send_json({"success": True, "curriculum": saved})

    def handle_save_paper(self):
        body = self.read_json_body()
        if not body or not body.get("subject_title") or not body.get("subject_code"):
            self.send_json({"error": "Subject title and subject code are required."}, 400)
            return

        pdf_bytes = None
        pdf_filename = body.get("pdf_filename")
        if body.get("pdf_base64"):
            try:
                b64_str = body["pdf_base64"]
                if "base64," in b64_str:
                    b64_str = b64_str.split("base64,")[1]
                pdf_bytes = base64.b64decode(b64_str)
            except Exception as e:
                self.send_json({"error": f"Invalid base64 PDF data: {e}"}, 400)
                return

        saved = campus_service.save_paper(body, pdf_bytes=pdf_bytes, pdf_filename=pdf_filename)
        self.send_json({"success": True, "paper": saved})

    def handle_campus_pdf_upload(self):
        content_type = self.headers.get('Content-Type', '')
        if content_type.startswith('application/json'):
            body = self.read_json_body()
            uni_id = body.get("university_id", "aktu").lower()
            orig_filename = body.get("filename", "uploaded_paper.pdf")
            b64_str = body.get("pdf_base64", "")
            if "base64," in b64_str:
                b64_str = b64_str.split("base64,")[1]
            try:
                file_bytes = base64.b64decode(b64_str)
            except Exception as e:
                self.send_json({"error": f"Base64 decode failed: {e}"}, 400)
                return
        elif content_type.startswith('multipart/form-data'):
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > 15 * 1024 * 1024: # 15MB limit
                self.send_json({"error": "File size must be greater than 0 and less than 15MB"}, 400)
                return

            boundary = content_type.split("boundary=")[-1].strip().encode('utf-8')
            raw_body = self.rfile.read(content_length)
            parts = raw_body.split(b'--' + boundary)
            file_bytes = None
            orig_filename = "exam_paper.pdf"
            uni_id = "aktu"

            for part in parts:
                if b'name="university_id"' in part:
                    _, _, val = part.partition(b'\r\n\r\n')
                    uni_id = val.strip().decode('utf-8', errors='ignore').lower() or "aktu"
                if b'filename="' in part:
                    headers_part, _, body_part = part.partition(b'\r\n\r\n')
                    match = re.search(r'filename="([^"]+)"', headers_part.decode('latin1', errors='ignore'))
                    if match:
                        orig_filename = match.group(1)
                    if body_part.endswith(b'\r\n'):
                        body_part = body_part[:-2]
                    file_bytes = body_part
        else:
            self.send_json({"error": "Unsupported Content-Type"}, 400)
            return

        if not file_bytes:
            self.send_json({"error": "No file received"}, 400)
            return

        clean_filename = re.sub(r'[^a-zA-Z0-9_.\-]+', '_', orig_filename)
        if not clean_filename.lower().endswith(".pdf"):
            clean_filename += ".pdf"

        target_dir = os.path.join(DIRECTORY, "Assest", "pyqs", uni_id)
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, clean_filename)

        with open(target_path, "wb") as f:
            f.write(file_bytes)

        pdf_url = f"/Assest/pyqs/{uni_id}/{clean_filename}"
        self.send_json({
            "success": True,
            "pdf_url": pdf_url,
            "filename": clean_filename,
            "size": len(file_bytes)
        })

    def handle_toggle_dsa_progress(self):
        body = self.read_json_body()
        problem_id = body.get('problem_id', '').strip()
        status = body.get('status', 'solved').strip()
        topic = body.get('topic', '')

        if not problem_id:
            self.send_json({"error": "problem_id is required"}, 400)
            return

        user = self.get_current_user()
        if not user:
            # Guest mode: respond OK with guest flag so front-end stores in localStorage
            self.send_json({
                "success": True,
                "guest": True,
                "problem_id": problem_id,
                "status": status,
                "active": True,
                "heatmap": {},
                "max_streak": 1
            })
            return

        active = toggle_user_dsa_problem(user["id"], problem_id, status=status, topic=topic)
        progress = get_user_dsa_progress(user["id"])
        profile = get_user_full_profile(user["id"])
        self.send_json({
            "success": True,
            "guest": False,
            "problem_id": problem_id,
            "status": status,
            "active": active,
            "solved": progress["solved"],
            "revision": progress["revision"],
            "streak": profile.get("streak_count", 1),
            "max_streak": max(profile.get("streak_count", 1), 1),
            "questions_solved_total": profile.get("questions_solved_total", 0),
            "heatmap": profile.get("heatmap", {})
        })

    # ------------------ Gallery & Community Projects Handlers ------------------

    def handle_gallery_posters_create(self):
        body = self.read_json_body()
        p = gallery_service.create_poster(body)
        self.send_json({"success": True, "poster": p})

    def handle_gallery_posters_update(self, poster_id):
        body = self.read_json_body()
        p = gallery_service.update_poster(poster_id, body)
        self.send_json({"success": True, "poster": p})

    def handle_previous_events_create(self):
        body = self.read_json_body()
        e = gallery_service.create_previous_event(body)
        self.send_json({"success": True, "event": e})

    def handle_previous_events_update(self, event_id):
        body = self.read_json_body()
        e = gallery_service.update_previous_event(event_id, body)
        self.send_json({"success": True, "event": e})

    def handle_community_project_create(self, user):
        body = self.read_json_body()
        if not body.get("title") or not body.get("description"):
            self.send_json({"error": "Title and description are required"}, 400)
            return
        proj = gallery_service.create_community_project(user["id"], body)
        self.send_json({"success": True, "project": proj})

    def handle_community_project_update(self, project_id, user):
        body = self.read_json_body()
        is_admin = user.get("role") == "admin"
        proj, err = gallery_service.update_community_project(project_id, user["id"], is_admin, body)
        if err:
            self.send_json({"error": err}, 400)
            return
        self.send_json({"success": True, "project": proj})

    def handle_community_project_delete(self, project_id, user):
        is_admin = user.get("role") == "admin"
        ok, err = gallery_service.delete_community_project(project_id, user["id"], is_admin)
        if not ok:
            self.send_json({"error": err or "Failed to delete project"}, 403)
            return
        self.send_json({"success": True})

    def handle_community_project_comment_create(self, project_id, user):
        body = self.read_json_body()
        msg = body.get("message", "").strip()
        parent_id = body.get("parent_id")
        if not msg:
            self.send_json({"error": "Message cannot be empty"}, 400)
            return
        comm, err = gallery_service.add_project_comment(project_id, user["id"], parent_id, msg)
        if err:
            self.send_json({"error": err}, 400)
            return

        # Automatically notify project owner in their notifications
        try:
            proj = gallery_service.get_community_project(project_id)
            if proj and proj.get("user_id") and proj["user_id"] != user["id"]:
                author_name = user.get("name") or user.get("email") or "A developer"
                snippet = msg[:60] + ("..." if len(msg) > 60 else "")
                db.create_notification(
                    title=f"💬 New comment on {proj.get('title', 'your project')}",
                    message=f"{author_name}: \"{snippet}\"",
                    link_url=f"gallery.html#project-{project_id}",
                    n_type="comment",
                    user_id=proj["user_id"]
                )
        except Exception as e:
            print(f"[Notification] Comment notice failed: {e}")

        self.send_json({"success": True, "comment": comm})

    def handle_community_project_comment_delete(self, comment_id, user):
        is_admin = user.get("role") == "admin"
        ok, err = gallery_service.delete_project_comment(comment_id, user["id"], is_admin)
        if not ok:
            self.send_json({"error": err or "Failed to delete comment"}, 403)
            return
        self.send_json({"success": True})

    def handle_gallery_upload(self, user):
        content_type = self.headers.get('Content-Type', '')
        file_bytes = None
        media_type = "gallery"

        if content_type.startswith('application/json'):
            body = self.read_json_body()
            media_type = body.get("media_type", "gallery")
            b64_str = body.get("image_base64") or body.get("image_data") or ""
            if "base64," in b64_str:
                b64_str = b64_str.split("base64,")[1]
            try:
                file_bytes = base64.b64decode(b64_str)
            except Exception as e:
                self.send_json({"error": f"Base64 decode failed: {e}"}, 400)
                return
        elif content_type.startswith('multipart/form-data'):
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > 10 * 1024 * 1024:
                self.send_json({"error": "File size must be greater than 0 and less than 10MB"}, 400)
                return

            boundary = content_type.split("boundary=")[-1].strip().encode('utf-8')
            raw_body = self.rfile.read(content_length)
            parts = raw_body.split(b'--' + boundary)

            for part in parts:
                if b'name="media_type"' in part:
                    _, _, val = part.partition(b'\r\n\r\n')
                    media_type = val.strip().decode('utf-8', errors='ignore') or "gallery"
                if b'filename="' in part:
                    headers_part, _, body_part = part.partition(b'\r\n\r\n')
                    if body_part.endswith(b'\r\n'):
                        body_part = body_part[:-2]
                    file_bytes = body_part
                    break
        else:
            self.send_json({"error": "Unsupported Content-Type"}, 400)
            return

        if not file_bytes:
            self.send_json({"error": "No image data provided"}, 400)
            return

        detected_ext = validate_image_magic(file_bytes) or 'png'
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        safe_name = f"gal_{media_type}_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}.{detected_ext}"
        target_path = os.path.join(UPLOADS_DIR, safe_name)

        with open(target_path, 'wb') as f:
            f.write(file_bytes)

        rel_url = f"Assest/uploads/{safe_name}"
        self.send_json({
            "success": True,
            "url": rel_url,
            "filename": safe_name
        })

    # ==========================================
    # CERTIFICATE HANDLERS
    # ==========================================
    def handle_certificate_verify(self):
        body = self.read_json_body()
        comp_id = body.get("competition_id", "").strip()
        query = body.get("query", "").strip()
        res = certificate_service.verify_and_fetch_certificate(comp_id, query)
        if not res.get("found"):
            self.send_json({"success": False, "found": False, "message": res.get("message", "Participant not found")}, 404)
            return
        self.send_json({"success": True, **res})

    def handle_certificate_report_issue(self):
        body = self.read_json_body()
        res = certificate_service.report_certificate_issue(body)
        self.send_json({"success": True, **res})

    def handle_certificate_save(self, user):
        body = self.read_json_body()
        res = certificate_service.save_competition(body, user_id=user.get("id"))
        self.send_json(res)

    def handle_certificate_update(self, comp_id, user):
        body = self.read_json_body()
        body["id"] = comp_id
        res = certificate_service.save_competition(body, user_id=user.get("id"))
        self.send_json(res)

    def handle_certificate_template_upload(self):
        content_type = self.headers.get('Content-Type', '')
        file_bytes = None

        if content_type.startswith('application/json'):
            body = self.read_json_body()
            b64_str = body.get("image_base64") or body.get("image_data") or ""
            if "base64," in b64_str:
                b64_str = b64_str.split("base64,")[1]
            try:
                file_bytes = base64.b64decode(b64_str)
            except Exception as e:
                self.send_json({"error": f"Base64 decode failed: {e}"}, 400)
                return
        elif content_type.startswith('multipart/form-data'):
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > 15 * 1024 * 1024:
                self.send_json({"error": "File size must be greater than 0 and less than 15MB"}, 400)
                return
            boundary = content_type.split("boundary=")[-1].strip().encode('utf-8')
            raw_body = self.rfile.read(content_length)
            parts = raw_body.split(b'--' + boundary)
            for part in parts:
                if b'filename="' in part:
                    headers_part, _, body_part = part.partition(b'\r\n\r\n')
                    if body_part.endswith(b'\r\n'):
                        body_part = body_part[:-2]
                    file_bytes = body_part
                    break
        else:
            self.send_json({"error": "Unsupported Content-Type"}, 400)
            return

        if not file_bytes:
            self.send_json({"error": "No image payload found"}, 400)
            return

        detected_ext = validate_image_magic(file_bytes) or 'jpg'
        os.makedirs(UPLOADS_DIR, exist_ok=True)
        safe_name = f"cert_tmpl_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}.{detected_ext}"
        target_path = os.path.join(UPLOADS_DIR, safe_name)

        with open(target_path, 'wb') as f:
            f.write(file_bytes)

        rel_url = f"Assest/uploads/{safe_name}"
        self.send_json({"success": True, "url": rel_url, "filename": safe_name})

    def handle_certificate_roster_upload(self, comp_id):
        content_type = self.headers.get('Content-Type', '')
        file_bytes = None
        orig_filename = "roster.xlsx"
        replace_existing = False

        if content_type.startswith('application/json'):
            body = self.read_json_body()
            replace_existing = bool(body.get("replace_existing", False))
            orig_filename = body.get("filename", "roster.xlsx")
            b64_str = body.get("file_base64") or body.get("file_data") or ""
            if "base64," in b64_str:
                b64_str = b64_str.split("base64,")[1]
            try:
                file_bytes = base64.b64decode(b64_str)
            except Exception as e:
                self.send_json({"error": f"Base64 decode failed: {e}"}, 400)
                return
        elif content_type.startswith('multipart/form-data'):
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length <= 0 or content_length > 25 * 1024 * 1024:
                self.send_json({"error": "File size must be between 1B and 25MB"}, 400)
                return
            boundary = content_type.split("boundary=")[-1].strip().encode('utf-8')
            raw_body = self.rfile.read(content_length)
            parts = raw_body.split(b'--' + boundary)
            for part in parts:
                if b'name="replace_existing"' in part:
                    _, _, val = part.partition(b'\r\n\r\n')
                    replace_existing = val.strip().decode('utf-8', errors='ignore') in ('1', 'true', 'True')
                if b'filename="' in part:
                    headers_part, _, body_part = part.partition(b'\r\n\r\n')
                    match = re.search(r'filename="([^"]+)"', headers_part.decode('latin1', errors='ignore'))
                    if match:
                        orig_filename = match.group(1)
                    if body_part.endswith(b'\r\n'):
                        body_part = body_part[:-2]
                    file_bytes = body_part
        else:
            self.send_json({"error": "Unsupported Content-Type"}, 400)
            return

        if not file_bytes:
            self.send_json({"error": "No roster file payload found"}, 400)
            return

        records = certificate_service.parse_roster_file(file_bytes, orig_filename)
        if not records:
            self.send_json({"error": "Could not extract any participant names or emails from file."}, 400)
            return

        count = certificate_service.import_participants_bulk(comp_id, records, replace_existing=replace_existing)
        self.send_json({
            "success": True,
            "imported_count": count,
            "sample": records[:10]
        })


def ensure_initial_setup():
    """Initializes tables, seeds initial data, and ensures admin user is provisioned."""
    init_db()

    admin_id = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = 'event@devengers.org'")
        admin = cursor.fetchone()
        admin_id = admin["id"] if admin else None
        conn.close()
    except Exception as e:
        print(f"[Admin Check] Error: {e}")

    if not admin_id:
        from auth import create_or_update_user
        env_pwd = os.environ.get("DEVENGERS_ADMIN_PASSWORD", "devengers@2026")
        created = create_or_update_user("event@devengers.org", env_pwd, role="admin", name="Devengers Event Admin")
        admin_id = created["id"]
        print(f"[Admin Setup] Provisioned event@devengers.org")

    seed_starter_events_if_empty(admin_id)
    seed_starter_courses_if_empty()

    try:
        gallery_service.init_gallery_tables()
    except Exception as e:
        print(f"[Gallery Init] Error initializing gallery tables: {e}")

    try:
        certificate_service.init_certificate_tables()
        certificate_service.seed_starter_certificates_if_empty(admin_id)
    except Exception as e:
        print(f"[Certificate Init] Error: {e}")


if __name__ == '__main__':
    ensure_initial_setup()
    
    # Start 11:59 PM IST daily automated job & internship crawler daemon
    try:
        from job_sync_service import start_daily_scheduler
        start_daily_scheduler()
    except Exception as e:
        print(f"[JOB SYNC] Could not start scheduler: {e}")

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), DevengersHandler) as httpd:
        print(f"Devengers Platform Server running on http://localhost:{PORT}")
        print("Ready for local testing.")
        httpd.serve_forever()
