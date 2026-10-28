"""
Database configuration and queries for Devengers Events Platform.
Uses SQLite for persistent storage with zero external dependencies.
"""

import sqlite3
import os
import uuid
from datetime import datetime, timezone, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "devengers.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            name TEXT,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)

    # Sessions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            ip_address TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Events Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            short_description TEXT NOT NULL,
            full_description TEXT,
            category TEXT NOT NULL CHECK(category IN ('Hackathons', 'Quizzes', 'Internships', 'Jobs')),
            organizer TEXT,
            thumbnail TEXT NOT NULL,
            reg_open_date TEXT,
            reg_deadline TEXT NOT NULL,
            event_start_date TEXT,
            event_end_date TEXT,
            prize_amount REAL,
            prize_currency TEXT DEFAULT 'INR',
            prize_description TEXT,
            reg_fee REAL DEFAULT 0,
            destination_url TEXT NOT NULL,
            action_label TEXT DEFAULT 'Register Now',
            status TEXT NOT NULL DEFAULT 'Draft' CHECK(status IN ('Draft', 'Published', 'Unpublished', 'Archived')),
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            archived_at TEXT,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # Login Attempts Table for Rate Limiting
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_or_email TEXT NOT NULL,
            attempted_at TEXT NOT NULL
        )
    """)

    # Courses / Learning Resources Table (Free & Paid CS Courses, Docs, Cheatsheets)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'free',
            thumbnail TEXT NOT NULL,
            what_you_learn TEXT NOT NULL,
            what_you_get TEXT NOT NULL,
            has_certificate INTEGER DEFAULT 1,
            tags TEXT,
            doc_url TEXT,
            destination_url TEXT NOT NULL,
            action_label TEXT DEFAULT 'Start Free Course',
            provider TEXT DEFAULT 'Devengers Academy',
            mode TEXT DEFAULT 'Online (Self-Paced)',
            status TEXT NOT NULL DEFAULT 'Published',
            order_index INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_deadline ON events(reg_deadline);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_courses_category ON courses(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_courses_type ON courses(type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status);")

    # Settings Table for System Configurations (Auto-Sync, schedule timings, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Sync Logs Table for Automated Daily Job Crawls
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            synced_at TEXT NOT NULL,
            source TEXT NOT NULL,
            jobs_added INTEGER NOT NULL,
            internships_added INTEGER NOT NULL,
            status TEXT NOT NULL,
            details TEXT
        )
    """)

    # User Course Completion / Progress Tracking Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_course_progress (
            user_id TEXT NOT NULL,
            course_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            completed_at TEXT NOT NULL,
            PRIMARY KEY (user_id, course_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
    """)

    # User Applications & Bookmarks for Jobs, Internships, Hackathons & Quizzes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_applications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            status TEXT DEFAULT 'Applied',
            notes TEXT,
            UNIQUE(user_id, event_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        )
    """)

    # User Study Activity / Contribution Heatmap Table (GitHub Style Graph)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_study_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            activity_date TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            points INTEGER NOT NULL DEFAULT 1,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_user_date ON user_study_activity(user_id, activity_date);")

    # User DSA Progress Table (Solved & Marked for Revision)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_dsa_progress (
            user_id TEXT NOT NULL,
            problem_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'solved',
            marked_at TEXT NOT NULL,
            PRIMARY KEY (user_id, problem_id, status),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dsa_progress_user ON user_dsa_progress(user_id);")

    # Notifications Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT, -- NULL for broadcast/all users
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT DEFAULT 'announcement', -- 'announcement', 'comment', 'event', 'system'
            link_url TEXT DEFAULT '#',
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);")

    # Notification Reads Table (Tracks who has read which notification)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_reads (
            user_id TEXT NOT NULL,
            notification_id TEXT NOT NULL,
            read_at TEXT NOT NULL,
            PRIMARY KEY (user_id, notification_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notif_reads_user ON notification_reads(user_id);")

    # Safe column additions for Users (Profile, Emoji Avatar, Banner, Bio, Streak, Academics & Coding Handles)
    for col, col_type, col_default in [
        ('avatar_emoji', 'TEXT', "'⚡'"),
        ('avatar_url', 'TEXT', "''"),
        ('banner_color', 'TEXT', "'gradient-purple'"),
        ('banner_url', 'TEXT', "''"),
        ('banner_fit', 'TEXT', "'cover'"),
        ('banner_aspect', 'TEXT', "'wide'"),
        ('bio', 'TEXT', "''"),
        ('target_role', 'TEXT', "'B.Tech CSE / Full Stack'"),
        ('streak_count', 'INTEGER', "1"),
        ('last_active_date', 'TEXT', "''"),
        ('college_name', 'TEXT', "'Engineering Institute'"),
        ('grad_year', 'TEXT', "'2027'"),
        ('github_handle', 'TEXT', "''"),
        ('leetcode_handle', 'TEXT', "''"),
        ('linkedin_url', 'TEXT', "''"),
        ('portfolio_url', 'TEXT', "''"),
        ('twitter_handle', 'TEXT', "''"),
        ('skills', 'TEXT', "'Python, JavaScript, React, DSA, SQL, Git'"),
        ('questions_solved_total', 'INTEGER', "0")
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type} DEFAULT {col_default};")
        except sqlite3.OperationalError:
            pass

    # Safe column additions for Jobs/Internships & Media fields
    for col, col_type, col_default in [
        ('location', 'TEXT', "'(Remote)'"),
        ('job_type', 'TEXT', "'Full Time'"),
        ('experience_level', 'TEXT', "'Entry Level'"),
        ('org_logo', 'TEXT', "NULL"),
        ('banner_fit', 'TEXT', "'cover'"),
        ('source', 'TEXT', "'manual'"),
        ('tags', 'TEXT', "''")
    ]:
        try:
            cursor.execute(f"ALTER TABLE events ADD COLUMN {col} {col_type} DEFAULT {col_default};")
        except sqlite3.OperationalError:
            pass

    # For Hackathons & Community Events, use Devengers official logo
    cursor.execute("UPDATE events SET thumbnail = 'Assest/devengers-logo.png' WHERE category NOT IN ('Jobs', 'Internships') AND thumbnail LIKE '%hackwithindia%'")
    cursor.execute("UPDATE events SET org_logo = 'Assest/devengers-logo.png' WHERE category NOT IN ('Jobs', 'Internships') AND (org_logo IS NULL OR org_logo LIKE '%hackwithindia%')")

    # For Jobs and Internships, NEVER use Devengers logo as default or fallback
    cursor.execute("""
        UPDATE events 
        SET thumbnail = 'Assest/company-default-logo.svg' 
        WHERE category IN ('Jobs', 'Internships') 
          AND (thumbnail LIKE '%devengers%' OR thumbnail LIKE '%hackwithindia%')
    """)
    cursor.execute("""
        UPDATE events 
        SET org_logo = NULL 
        WHERE category IN ('Jobs', 'Internships') 
          AND (org_logo LIKE '%devengers%' OR org_logo LIKE '%hackwithindia%')
    """)

    # Initial default settings
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('auto_sync_enabled', 'true', datetime('now'))")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('sync_schedule_time', '23:59', datetime('now'))")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('last_sync_time', '', datetime('now'))")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('last_sync_count', '0', datetime('now'))")

    # Paid Courses Coming Soon Settings (Devengers Elite Pro Masterclasses)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('paid_coming_soon_enabled', 'true', datetime('now'))")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('paid_coming_soon_title', 'Devengers Elite Pro', datetime('now'))")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('paid_coming_soon_badge', 'COMING SOON // ELITE PRO', datetime('now'))")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('paid_coming_soon_subtitle', 'Upcoming cohort masterclasses in Web Dev, DSA, and winning national & global hackathons.', datetime('now'))")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES ('paid_coming_soon_date', 'Winter 2026', datetime('now'))")

    # Ensure updated title/badge values if already in DB
    cursor.execute("UPDATE settings SET value = 'Devengers Elite Pro' WHERE key = 'paid_coming_soon_title' AND value LIKE '%Mentorship%'")
    cursor.execute("UPDATE settings SET value = 'COMING SOON // ELITE PRO' WHERE key = 'paid_coming_soon_badge' AND value LIKE '%LAUNCHING%'")
    cursor.execute("UPDATE settings SET value = 'Upcoming cohort masterclasses in Web Dev, DSA, and winning national & global hackathons.' WHERE key = 'paid_coming_soon_subtitle' AND value LIKE '%bootcamps%'")

    conn.commit()
    conn.close()

    try:
        import gallery_service
        gallery_service.init_gallery_tables()
    except Exception as e:
        print(f"[GalleryService] Error initializing gallery tables: {e}")

def get_setting(key, default=None):
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute("""
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (key, str(value), now_iso))
    conn.commit()
    conn.close()

def record_sync_log(source, jobs_added, internships_added, status, details=''):
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute("""
        INSERT INTO sync_logs (synced_at, source, jobs_added, internships_added, status, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_iso, source, jobs_added, internships_added, status, details))
    conn.commit()
    conn.close()

def get_recent_sync_logs(limit=10):
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sync_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def seed_starter_events_if_empty(admin_id=None):
    """Seed initial published events across categories if table is empty"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM events")
    count = cursor.fetchone()["count"]

    if count == 0:
        now_iso = datetime.now(timezone.utc).isoformat()
        sample_events = [
            {
                "id": str(uuid.uuid4()),
                "title": "Devengers National AI Hackathon 2026",
                "short_description": "Build production-grade Generative AI agents and full-stack solutions. Network with top mentors and win cash prizes.",
                "full_description": "Join India's premier student and developer hackathon. 36 hours of relentless innovation, live workshops, mentor office hours, and national spotlight.",
                "category": "Hackathons",
                "organizer": "Devengers Tech Community",
                "thumbnail": "Assest/devengers-logo.png",
                "reg_open_date": "2026-10-01T00:00:00Z",
                "reg_deadline": "2026-11-15T23:59:59Z",
                "event_start_date": "2026-11-20T10:00:00Z",
                "event_end_date": "2026-11-22T18:00:00Z",
                "prize_amount": 100000.0,
                "prize_currency": "INR",
                "prize_description": "₹1,00,000 Total Pool + Cloud Credits + Swags",
                "reg_fee": 0.0,
                "destination_url": "https://whatsapp.com/channel/0029VbCVGAd8KMql7Ie3ew43",
                "action_label": "Register Now",
                "status": "Published",
                "created_by": admin_id,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "DSA & System Design Championship Quiz",
                "short_description": "Test your algorithms, data structures, and distributed systems fundamentals in a rapid-fire competitive quiz.",
                "full_description": "Live timed challenges covering Dynamic Programming, Graph Theory, System Scaling, and High Availability. Top performers receive referral perks.",
                "category": "Quizzes",
                "organizer": "Devengers DSA Guild",
                "thumbnail": "Assest/images Homepage/1.png",
                "reg_open_date": "2026-10-05T00:00:00Z",
                "reg_deadline": "2026-11-10T20:00:00Z",
                "event_start_date": "2026-11-11T18:00:00Z",
                "event_end_date": "2026-11-11T20:00:00Z",
                "prize_amount": 25000.0,
                "prize_currency": "INR",
                "prize_description": "₹25,000 + Hall of Fame Badge",
                "reg_fee": 0.0,
                "destination_url": "https://whatsapp.com/channel/0029VbCVGAd8KMql7Ie3ew43",
                "action_label": "Enter Quiz",
                "status": "Published",
                "created_by": admin_id,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Summer 2027 Software Engineering Internship",
                "short_description": "Direct fast-track internship recruitment opportunity for frontend, backend, and full-stack builders across our partner network.",
                "full_description": "Gain hands-on experience building scalable applications, CI/CD pipelines, and microservices alongside senior engineers.",
                "category": "Internships",
                "organizer": "Devengers CareerHub",
                "thumbnail": "Assest/devfolio-logo.png",
                "reg_open_date": "2026-10-10T00:00:00Z",
                "reg_deadline": "2026-11-30T23:59:59Z",
                "event_start_date": "2027-01-10T09:00:00Z",
                "event_end_date": "2027-06-30T17:00:00Z",
                "prize_amount": 45000.0,
                "prize_currency": "INR",
                "prize_description": "₹45,000 / month Stipend + PPO Opportunity",
                "reg_fee": 0.0,
                "destination_url": "https://unstop.com/internships",
                "action_label": "Apply for Internship",
                "status": "Published",
                "created_by": admin_id,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Junior Full-Stack Developer Opening",
                "short_description": "Full-time position for strong JavaScript/TypeScript, Python, and UI/UX developers. Competitive package with remote flexibility.",
                "full_description": "Join an innovative tech team developing high-traffic web platforms and developer tooling. Equity and healthcare benefits included.",
                "category": "Jobs",
                "organizer": "Devengers Partner Studio",
                "thumbnail": "Assest/webhurry-logo.png",
                "reg_open_date": "2026-10-12T00:00:00Z",
                "reg_deadline": "2026-12-05T23:59:59Z",
                "event_start_date": "2027-01-01T09:00:00Z",
                "event_end_date": None,
                "prize_amount": 800000.0,
                "prize_currency": "INR",
                "prize_description": "8 - 12 LPA CTC + Benefits",
                "reg_fee": 0.0,
                "destination_url": "https://unstop.com/jobs",
                "action_label": "Apply Now",
                "status": "Published",
                "created_by": admin_id,
                "created_at": now_iso,
                "updated_at": now_iso
            }
        ]

        for e in sample_events:
            cursor.execute("""
                INSERT INTO events (
                    id, title, short_description, full_description, category, organizer,
                    thumbnail, reg_open_date, reg_deadline, event_start_date, event_end_date,
                    prize_amount, prize_currency, prize_description, reg_fee,
                    destination_url, action_label, status, created_by, created_at, updated_at
                ) VALUES (
                    :id, :title, :short_description, :full_description, :category, :organizer,
                    :thumbnail, :reg_open_date, :reg_deadline, :event_start_date, :event_end_date,
                    :prize_amount, :prize_currency, :prize_description, :reg_fee,
                    :destination_url, :action_label, :status, :created_by, :created_at, :updated_at
                )
            """, e)
        conn.commit()

    conn.close()

def seed_starter_courses_if_empty(force_reseed=False):
    """Seed comprehensive free CS & B.Tech courses, roadmaps, and documentation across multiple platforms."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM courses")
    count = cursor.fetchone()["count"]

    if count == 0 or force_reseed:
        if force_reseed:
            cursor.execute("DELETE FROM courses")
            conn.commit()

        now_iso = datetime.now(timezone.utc).isoformat()
        sample_courses = [
            # 1. WEB DEVELOPMENT
            {
                "id": str(uuid.uuid4()),
                "title": "Full Stack Web Development Certification",
                "category": "Web Development",
                "type": "free",
                "thumbnail": "https://images.unsplash.com/photo-1593720213428-28a5b9e94613?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• HTML5 & Modern CSS3 Flexbox/Grid Layouts\n• JavaScript ES6+, Asynchronous Fetch & DOM APIs\n• React.js Components, State Management & Node.js Backend",
                "what_you_get": "🎓 Free Verified Certificate • 🛠️ 5 Real-World Projects • ⚡ Lifetime Free Access",
                "has_certificate": 1,
                "tags": "Web Dev, JavaScript, React, Node.js, Free Certificate, B.Tech CSE",
                "doc_url": "https://developer.mozilla.org/en-US/docs/Learn",
                "destination_url": "https://www.freecodecamp.org/learn/full-stack-developer/",
                "action_label": "Start Free Course",
                "provider": "freeCodeCamp",
                "mode": "Online (Self-Paced)",
                "status": "Published",
                "order_index": 1,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "MDN Web Docs: Frontend & Backend Engineering Standards",
                "category": "Web Development",
                "type": "doc",
                "thumbnail": "https://images.unsplash.com/photo-1507238691740-187a5b1d37b8?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Complete HTML5 & CSS3 Tag Reference & Web APIs\n• JavaScript Event Loop, Prototypal Inheritance & Async/Await\n• Modern Web Security, HTTPS & Performance Standards",
                "what_you_get": "📄 Official W3C Standards Reference • 💻 Interactive Code Sandboxes • 🎯 Topic Roadmaps",
                "has_certificate": 0,
                "tags": "HTML, CSS, JavaScript, Web Standards, Official Docs, B.Tech CSE",
                "doc_url": "https://developer.mozilla.org/en-US/docs/Learn",
                "destination_url": "https://developer.mozilla.org/en-US/docs/Learn",
                "action_label": "Read Official Docs",
                "provider": "Mozilla Developer Network",
                "mode": "Official Documentation",
                "status": "Published",
                "order_index": 2,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "The Odin Project: Full Stack JavaScript Curriculum",
                "category": "Web Development",
                "type": "free",
                "thumbnail": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Terminal Commands, Git & Professional GitHub Workflows\n• Deep JavaScript ES6+, OOP & Async Architectures\n• Full Stack React, Express & PostgreSQL Database Design",
                "what_you_get": "🛠️ 12+ Open-Source Capstones • 👥 Global Discord Community • 📚 100% Free Open Source",
                "has_certificate": 0,
                "tags": "Web Dev, JavaScript, Open Source, Git, Full Stack, B.Tech CSE",
                "doc_url": "https://www.theodinproject.com/paths/full-stack-javascript",
                "destination_url": "https://www.theodinproject.com/paths/full-stack-javascript",
                "action_label": "Explore Curriculum",
                "provider": "The Odin Project",
                "mode": "Online (Project-Based)",
                "status": "Published",
                "order_index": 3,
                "created_at": now_iso,
                "updated_at": now_iso
            },

            # 2. DSA & ALGORITHMS
            {
                "id": str(uuid.uuid4()),
                "title": "Striver's A2Z DSA Course & SDE Sheet",
                "category": "DSA & Algorithms",
                "type": "free",
                "thumbnail": "https://images.unsplash.com/photo-1515879218367-8466d910aaa4?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Arrays, Strings, Two Pointers & Hashing Patterns\n• Binary Trees, BST, Graphs (BFS/DFS/Dijkstra) & Tries\n• Dynamic Programming (1D/2D Grids, Subsequences & MCM)",
                "what_you_get": "🎯 450+ Curated Problems • 📹 Free Video Solutions • 📄 Downloadable SDE Sheet",
                "has_certificate": 1,
                "tags": "DSA, C++, Java, Algorithms, SDE Sheet, FAANG Prep, B.Tech CSE",
                "doc_url": "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2/",
                "destination_url": "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2/",
                "action_label": "Start DSA Sheet",
                "provider": "TakeUForward (Striver)",
                "mode": "Online (Video + Sheet)",
                "status": "Published",
                "order_index": 4,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "CS50x: Introduction to Computer Science",
                "category": "DSA & Algorithms",
                "type": "free",
                "thumbnail": "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Computational Thinking, Problem Solving & Algorithms in C\n• Memory Pointers, Dynamic Allocation & Classic Linked Lists\n• Python, SQL, Web Frontend & Big-O Asymptotic Complexity",
                "what_you_get": "🎓 Official Free Harvard CS50 Certificate • 🛠️ 9 Guided Lab Problem Sets • ⚡ World-Class Lectures",
                "has_certificate": 1,
                "tags": "Computer Science, C, Python, Harvard, Algorithms, Free Certificate, B.Tech CSE",
                "doc_url": "https://cs50.harvard.edu/x/",
                "destination_url": "https://cs50.harvard.edu/x/",
                "action_label": "Enroll on CS50x",
                "provider": "Harvard University",
                "mode": "Online Masterclass",
                "status": "Published",
                "order_index": 5,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Interactive DSA Visualizations & Algorithms Library",
                "category": "DSA & Algorithms",
                "type": "doc",
                "thumbnail": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Animated Tracing for Sorting, Searching & Tree Rotations\n• Recursion, Backtracking & Graph Traversal Visualizers\n• Big O Time & Space Complexity Side-by-Side Comparisons",
                "what_you_get": "💻 Interactive Visual Sandbox • 📑 Step-by-Step Code Tracing • 🏆 100+ Visual Demos",
                "has_certificate": 0,
                "tags": "DSA, Visualizations, Algorithms, Interactive, B.Tech CSE",
                "doc_url": "https://github.com/trekhleb/javascript-algorithms",
                "destination_url": "https://visualgo.net/en",
                "action_label": "Explore DSA Visuals",
                "provider": "VisuAlgo & Open Source Guild",
                "mode": "Interactive Visualizer",
                "status": "Published",
                "order_index": 6,
                "created_at": now_iso,
                "updated_at": now_iso
            },

            # 3. AI & MACHINE LEARNING
            {
                "id": str(uuid.uuid4()),
                "title": "Machine Learning Specialization",
                "category": "AI & Machine Learning",
                "type": "free",
                "thumbnail": "https://images.unsplash.com/photo-1555949963-ff9fe0c870eb?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Supervised Machine Learning: Linear/Logistic Regression & Cost Functions\n• Deep Learning: Multi-Layer Perceptrons & TensorFlow 2.x\n• Unsupervised Learning: Clustering, PCA & Recommendation Systems",
                "what_you_get": "📊 Comprehensive Lecture Notes • 🧪 Python Jupyter Notebooks • 📄 Mathematical References",
                "has_certificate": 0,
                "tags": "AI, Machine Learning, Python, TensorFlow, Andrew Ng, Stanford, B.Tech CSE",
                "doc_url": "https://www.deeplearning.ai/courses/machine-learning-specialization/",
                "destination_url": "https://www.coursera.org/specializations/machine-learning-introduction",
                "action_label": "Explore ML Track",
                "provider": "DeepLearning.AI & Stanford",
                "mode": "Online (Self-Paced)",
                "status": "Published",
                "order_index": 7,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Google Machine Learning Crash Course with TensorFlow",
                "category": "AI & Machine Learning",
                "type": "free",
                "thumbnail": "https://images.unsplash.com/photo-1677442136019-21780ecad995?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Model Training Cycles, Loss Functions & Gradient Descent\n• Feature Engineering, Normalization & Embeddings\n• Multi-Class Neural Networks & Introduction to LLMs",
                "what_you_get": "⚡ Interactive Google Colab Notebooks • 📊 30+ Video Lessons • 📄 Official Google AI Guide",
                "has_certificate": 0,
                "tags": "Google AI, TensorFlow, Deep Learning, Python, Colab, Labs, B.Tech CSE",
                "doc_url": "https://developers.google.com/machine-learning/crash-course",
                "destination_url": "https://developers.google.com/machine-learning/crash-course",
                "action_label": "Start Google ML Course",
                "provider": "Google AI",
                "mode": "Interactive Tutorials & Colab",
                "status": "Published",
                "order_index": 8,
                "created_at": now_iso,
                "updated_at": now_iso
            },

            # 4. CORE CS & SYSTEMS
            {
                "id": str(uuid.uuid4()),
                "title": "Operating Systems: Three Easy Pieces (OSTEP)",
                "category": "Core CS & Systems",
                "type": "pdf",
                "thumbnail": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Virtualization: Processes, CPU Scheduling & Context Switches\n• Memory: Paging, Address Translation, TLBs & Swapping\n• Concurrency: Threads, Locks, Condition Variables & Deadlocks",
                "what_you_get": "📄 Free Complete Textbook PDF (All Chapters) • 💻 C Homework Code & Simulators • 📑 Exam Guides",
                "has_certificate": 0,
                "tags": "Operating Systems, C, Linux, Concurrency, PDF Textbook, B.Tech CSE",
                "doc_url": "https://pages.cs.wisc.edu/~remzi/OSTEP/",
                "destination_url": "https://pages.cs.wisc.edu/~remzi/OSTEP/",
                "action_label": "Download Free PDF Book",
                "provider": "University of Wisconsin-Madison",
                "mode": "Textbook & PDF Guide",
                "status": "Published",
                "order_index": 9,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Computer Networks: Stanford CS144 & Protocols Reference",
                "category": "Core CS & Systems",
                "type": "doc",
                "thumbnail": "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• OSI 7-Layer & TCP/IP Architecture Models\n• IP Addressing, Subnetting & Routing (OSPF, BGP)\n• TCP Flow/Congestion Control & HTTP/3 WebSockets",
                "what_you_get": "📄 Protocol Reference Guide • 💻 Wireshark Packet Analysis Labs • 📑 Campus Placement Q&A",
                "has_certificate": 0,
                "tags": "Computer Networks, TCP/IP, Socket Programming, Protocols, B.Tech CSE",
                "doc_url": "https://cs144.github.io/",
                "destination_url": "https://cs144.github.io/",
                "action_label": "Read Networking Docs",
                "provider": "Stanford University",
                "mode": "Documentation & Notes",
                "status": "Published",
                "order_index": 10,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Database Management Systems (DBMS) & SQL Masterclass",
                "category": "Core CS & Systems",
                "type": "free",
                "thumbnail": "https://images.unsplash.com/photo-1544383835-bda2bc66a55d?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Relational Data Model, ER Diagrams & Schema Normalization\n• SQL Mastery: Complex Joins, Window Functions & CTEs\n• Transactions, Concurrency Control, 2PL & ACID Properties",
                "what_you_get": "📄 SQL Cheatsheet & Query Guide • 💻 100+ SQL Practice Queries • 🎓 Free Certificate Option",
                "has_certificate": 1,
                "tags": "DBMS, SQL, Relational Databases, Normalization, Free Certificate, B.Tech CSE",
                "doc_url": "https://quickref.me/mysql",
                "destination_url": "https://www.freecodecamp.org/news/sql-and-databases-full-course/",
                "action_label": "Master DBMS & SQL",
                "provider": "CMU DB Group & freeCodeCamp",
                "mode": "Online & Interactive",
                "status": "Published",
                "order_index": 11,
                "created_at": now_iso,
                "updated_at": now_iso
            },

            # 5. CHEATSHEETS & PDFS
            {
                "id": str(uuid.uuid4()),
                "title": "B.Tech CSE QuickRef & Tech Interview Handbook",
                "category": "Cheatsheets & PDFs",
                "type": "pdf",
                "thumbnail": "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Data Structures & Algorithms Quick Formula Sheet\n• Operating Systems Process States & Deadlock Conditions\n• Computer Networks Subnetting, Headers & Protocol Ports",
                "what_you_get": "📄 Comprehensive Developer Cheatsheets • 🎯 Algorithm & System Design Guides • 📑 Quick Revision",
                "has_certificate": 0,
                "tags": "PDF Notes, Cheatsheets, B.Tech CSE, Quick Revision, Free Download",
                "doc_url": "https://www.techinterviewhandbook.org/",
                "destination_url": "https://quickref.me/",
                "action_label": "View Developer Cheat Sheets",
                "provider": "QuickRef & Tech Interview Handbook",
                "mode": "Online Reference & Sheets",
                "status": "Published",
                "order_index": 12,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Modern JavaScript Cheatsheet & PDF Guide",
                "category": "Cheatsheets & PDFs",
                "type": "pdf",
                "thumbnail": "https://images.unsplash.com/photo-1579468118864-1b9ea3c0db4a?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• ES6+ Arrow Functions, Destructuring & Rest/Spread Syntax\n• Promises, Async/Await & Microtask Execution Order\n• Closures, Prototypes & Modern Modules Architecture",
                "what_you_get": "📄 Official GitHub Cheatsheet • 💻 Code Snippets & Anti-Patterns • 📑 Printable Reference",
                "has_certificate": 0,
                "tags": "JavaScript, ES6, Frontend, Cheatsheet, PDF, B.Tech CSE",
                "doc_url": "https://github.com/mbeaudru/modern-js-cheatsheet",
                "destination_url": "https://github.com/mbeaudru/modern-js-cheatsheet",
                "action_label": "Open JavaScript Cheatsheet",
                "provider": "Modern JS Open Source",
                "mode": "Reference & PDF Guide",
                "status": "Published",
                "order_index": 13,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "C++ & STL Algorithms Quick Reference Sheet for DSA",
                "category": "Cheatsheets & PDFs",
                "type": "pdf",
                "thumbnail": "https://images.unsplash.com/photo-1515879218367-8466d910aaa4?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Standard Template Library: Vector, Map, Set, Priority Queue\n• Built-in Binary Search, Sort & Permutations Functions\n• Memory Management, Lambda Expressions & Complexity Rules",
                "what_you_get": "📄 Fast C++ STL Lookup • 🎯 Competitive Programming Shortcuts • 📑 Formula Card",
                "has_certificate": 0,
                "tags": "C++, STL, DSA, Cheatsheet, Competitive Programming, B.Tech CSE",
                "doc_url": "https://quickref.me/cpp",
                "destination_url": "https://quickref.me/cpp",
                "action_label": "View C++ STL Cheatsheet",
                "provider": "QuickRef Engineering",
                "mode": "Quick Reference Sheet",
                "status": "Published",
                "order_index": 14,
                "created_at": now_iso,
                "updated_at": now_iso
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Git & GitHub Command Architecture Cheat Sheet",
                "category": "Cheatsheets & PDFs",
                "type": "pdf",
                "thumbnail": "https://images.unsplash.com/photo-1618401471353-b98aedd04e11?auto=format&fit=crop&w=1200&q=80",
                "what_you_learn": "• Essential Branching, Merging & Rebase Interactive Workflows\n• Resolving Merge Conflicts, Stashing & Commit Amending\n• Remote Upstream Syncing, SSH Keys & Pull Request Etiquette",
                "what_you_get": "📄 Visual Git Workflow Diagram • 💻 Everyday Terminal Commands • 📑 Troubleshooting Sheet",
                "has_certificate": 0,
                "tags": "Git, GitHub, Version Control, Terminal, Cheatsheet, B.Tech CSE",
                "doc_url": "https://quickref.me/git",
                "destination_url": "https://quickref.me/git",
                "action_label": "Open Git Cheatsheet",
                "provider": "Devengers Open Source Guild",
                "mode": "Terminal Cheatsheet",
                "status": "Published",
                "order_index": 15,
                "created_at": now_iso,
                "updated_at": now_iso
            }
        ]

        for c in sample_courses:
            cursor.execute("""
                INSERT INTO courses (
                    id, title, category, type, thumbnail, what_you_learn, what_you_get,
                    has_certificate, tags, doc_url, destination_url, action_label,
                    provider, mode, status, order_index, created_at, updated_at
                ) VALUES (
                    :id, :title, :category, :type, :thumbnail, :what_you_learn, :what_you_get,
                    :has_certificate, :tags, :doc_url, :destination_url, :action_label,
                    :provider, :mode, :status, :order_index, :created_at, :updated_at
                )
            """, c)
        conn.commit()
        print(f"[Learn Seed] Seeded {len(sample_courses)} curated free courses & resources.")

    conn.close()

def get_courses(category=None, course_type=None, status=None, search=None, limit=200):
    """Fetches courses with optional filters for category, type (free, paid, doc, pdf), status, and search."""
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM courses WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)

    if category and category.lower() != 'all':
        query += " AND category = ?"
        params.append(category)

    if course_type and course_type.lower() != 'all':
        query += " AND type = ?"
        params.append(course_type)

    if search:
        search_pattern = f"%{search.strip()}%"
        query += " AND (title LIKE ? OR what_you_learn LIKE ? OR what_you_get LIKE ? OR tags LIKE ? OR provider LIKE ?)"
        params.extend([search_pattern, search_pattern, search_pattern, search_pattern, search_pattern])

    query += " ORDER BY order_index ASC, created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_course(course_id):
    """Fetches a single course by ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_course(data):
    """Creates a new course entry."""
    conn = get_connection()
    cursor = conn.cursor()
    course_id = data.get('id') or str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO courses (
            id, title, category, type, thumbnail, what_you_learn, what_you_get,
            has_certificate, tags, doc_url, destination_url, action_label,
            provider, mode, status, order_index, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
    """, (
        course_id,
        data.get('title', '').strip(),
        data.get('category', 'Web Development').strip(),
        data.get('type', 'free').strip(),
        data.get('thumbnail', 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&w=1200&q=80').strip(),
        data.get('what_you_learn', '').strip(),
        data.get('what_you_get', '').strip(),
        1 if data.get('has_certificate') in (1, '1', True, 'true') else 0,
        data.get('tags', '').strip(),
        data.get('doc_url', '').strip() or None,
        data.get('destination_url', '').strip(),
        data.get('action_label', 'Start Free Course').strip(),
        data.get('provider', 'Devengers Academy').strip(),
        data.get('mode', 'Online (Self-Paced)').strip(),
        data.get('status', 'Published').strip(),
        int(data.get('order_index', 0)),
        now_iso,
        now_iso
    ))
    conn.commit()
    conn.close()
    return get_course(course_id)

def update_course(course_id, data):
    """Updates an existing course entry."""
    conn = get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        UPDATE courses SET
            title = ?,
            category = ?,
            type = ?,
            thumbnail = ?,
            what_you_learn = ?,
            what_you_get = ?,
            has_certificate = ?,
            tags = ?,
            doc_url = ?,
            destination_url = ?,
            action_label = ?,
            provider = ?,
            mode = ?,
            status = ?,
            order_index = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        data.get('title', '').strip(),
        data.get('category', 'Web Development').strip(),
        data.get('type', 'free').strip(),
        data.get('thumbnail', '').strip(),
        data.get('what_you_learn', '').strip(),
        data.get('what_you_get', '').strip(),
        1 if data.get('has_certificate') in (1, '1', True, 'true') else 0,
        data.get('tags', '').strip(),
        data.get('doc_url', '').strip() or None,
        data.get('destination_url', '').strip(),
        data.get('action_label', 'Start Free Course').strip(),
        data.get('provider', 'Devengers Academy').strip(),
        data.get('mode', 'Online (Self-Paced)').strip(),
        data.get('status', 'Published').strip(),
        int(data.get('order_index', 0)),
        now_iso,
        course_id
    ))
    conn.commit()
    conn.close()
    return get_course(course_id)

def delete_course(course_id):
    """Deletes a course entry."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    conn.commit()
    conn.close()
    return True

def get_learn_settings():
    """Retrieves all settings related to the Learn page & Coming Soon section."""
    return {
        "paid_coming_soon_enabled": get_setting("paid_coming_soon_enabled", "true").lower() in ("true", "1", "yes"),
        "paid_coming_soon_title": get_setting("paid_coming_soon_title", "Devengers Elite Pro"),
        "paid_coming_soon_badge": get_setting("paid_coming_soon_badge", "COMING SOON // ELITE PRO"),
        "paid_coming_soon_subtitle": get_setting("paid_coming_soon_subtitle", "Upcoming cohort masterclasses in Web Dev, DSA, and winning national & global hackathons."),
        "paid_coming_soon_date": get_setting("paid_coming_soon_date", "Winter 2026")
    }

def update_learn_settings(settings_dict):
    """Updates settings for Learn page."""
    for key in ("paid_coming_soon_enabled", "paid_coming_soon_title", "paid_coming_soon_badge", "paid_coming_soon_subtitle", "paid_coming_soon_date"):
        if key in settings_dict:
            val = settings_dict[key]
            if isinstance(val, bool):
                val = "true" if val else "false"
            set_setting(key, str(val))
    return get_learn_settings()




# ------------------ User Course Progress & Completion ------------------

def toggle_user_course_progress(user_id, course_id):
    """Toggles completion status for a course for a logged-in user and logs activity for heatmap."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM user_course_progress WHERE user_id = ? AND course_id = ?", (user_id, course_id))
    row = cursor.fetchone()
    now_iso = datetime.now(timezone.utc).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if row:
        cursor.execute("DELETE FROM user_course_progress WHERE user_id = ? AND course_id = ?", (user_id, course_id))
        completed = False
    else:
        cursor.execute("""
            INSERT INTO user_course_progress (user_id, course_id, status, completed_at)
            VALUES (?, ?, 'completed', ?)
        """, (user_id, course_id, now_iso))
        completed = True
        # Log 3 study points on the GitHub-style activity graph for completing a course!
        cursor.execute("""
            INSERT INTO user_study_activity (user_id, activity_date, activity_type, points, details, created_at)
            VALUES (?, ?, 'course_completed', 3, ?, ?)
        """, (user_id, today_str, f"Completed Course: {course_id}", now_iso))

    conn.commit()
    conn.close()
    return completed

def get_user_completed_courses(user_id):
    """Returns full details of all courses completed by the user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, ucp.completed_at
        FROM user_course_progress ucp
        JOIN courses c ON ucp.course_id = c.id
        WHERE ucp.user_id = ?
        ORDER BY ucp.completed_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_completed_course_ids(user_id):
    """Returns list of course IDs completed by the user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT course_id FROM user_course_progress WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r["course_id"] for r in rows]

# ------------------ User Study Activity & GitHub-Style Heatmap ------------------

def log_study_activity(user_id, activity_type, points=1, details="", activity_date=None):
    """Logs study activity or question solving for the user heatmap."""
    conn = get_connection()
    cursor = conn.cursor()
    now_dt = datetime.now(timezone.utc)
    date_str = activity_date or now_dt.strftime("%Y-%m-%d")
    now_iso = now_dt.isoformat()
    cursor.execute("""
        INSERT INTO user_study_activity (user_id, activity_date, activity_type, points, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, date_str, activity_type, points, details, now_iso))
    conn.commit()
    conn.close()

def get_user_study_heatmap(user_id):
    """Returns a map of { YYYY-MM-DD: total_points } for rendering the GitHub-style activity graph."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT activity_date, SUM(points) as total_points, COUNT(*) as activity_count
        FROM user_study_activity
        WHERE user_id = ?
        GROUP BY activity_date
    """, (user_id,))
    rows = cursor.fetchall()
    
    heatmap_map = {}
    for r in rows:
        heatmap_map[r["activity_date"]] = r["total_points"]
        
    # Also incorporate DSA problem solved dates from user_dsa_progress
    try:
        cursor.execute("""
            SELECT substr(marked_at, 1, 10) as act_date, COUNT(*) as dsa_cnt
            FROM user_dsa_progress
            WHERE user_id = ? AND status = 'solved'
            GROUP BY act_date
        """, (user_id,))
        for r in cursor.fetchall():
            d = r["act_date"]
            if d:
                heatmap_map[d] = max(heatmap_map.get(d, 0), r["dsa_cnt"])
    except Exception:
        pass

    conn.close()
    return heatmap_map

def log_user_questions_solved(user_id, count=1, topic=""):
    """Increments questions solved counter and adds study points to darken the GitHub heatmap."""
    if count <= 0:
        return get_user_full_profile(user_id)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET questions_solved_total = COALESCE(questions_solved_total, 0) + ? 
        WHERE id = ?
    """, (count, user_id))
    conn.commit()
    conn.close()
    log_study_activity(user_id, "questions_solved", points=count, details=topic or f"Solved {count} questions")
    return get_user_full_profile(user_id)

# ------------------ User Applied Events & Opportunities ------------------

def toggle_user_application(user_id, event_id):
    """Toggles application / tracking status for a job, internship, hackathon, or quiz."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM user_applications WHERE user_id = ? AND event_id = ?", (user_id, event_id))
    row = cursor.fetchone()
    now_iso = datetime.now(timezone.utc).isoformat()
    if row:
        cursor.execute("DELETE FROM user_applications WHERE user_id = ? AND event_id = ?", (user_id, event_id))
        applied = False
    else:
        app_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO user_applications (id, user_id, event_id, applied_at, status)
            VALUES (?, ?, ?, ?, 'Applied')
        """, (app_id, user_id, event_id, now_iso))
        applied = True
    conn.commit()
    conn.close()
    return applied

def get_user_applied_events(user_id):
    """Returns all opportunities applied to by the user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.*, ua.applied_at, ua.status as app_status
        FROM user_applications ua
        JOIN events e ON ua.event_id = e.id
        WHERE ua.user_id = ?
        ORDER BY ua.applied_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_applied_event_ids(user_id):
    """Returns list of event IDs applied to by user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT event_id FROM user_applications WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r["event_id"] for r in rows]

# ------------------ User Profile & Academics ------------------

def calculate_user_streak(user_id):
    """Calculates consecutive active days dynamically based on real activity logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT activity_date FROM user_study_activity WHERE user_id = ?
        UNION
        SELECT DISTINCT substr(marked_at, 1, 10) as activity_date FROM user_dsa_progress WHERE user_id = ?
    """, (user_id, user_id))
    rows = cursor.fetchall()
    active_dates = set(r[0] for r in rows if r[0])

    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    yesterday_str = (today_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    streak = 0
    if today_str in active_dates:
        streak = 1
        cur = today_dt - timedelta(days=1)
        while cur.strftime("%Y-%m-%d") in active_dates:
            streak += 1
            cur -= timedelta(days=1)
    elif yesterday_str in active_dates:
        streak = 1
        cur = today_dt - timedelta(days=2)
        while cur.strftime("%Y-%m-%d") in active_dates:
            streak += 1
            cur -= timedelta(days=1)
    elif len(active_dates) > 0:
        streak = 0
    else:
        streak = 0

    # Persist the accurate streak in users table
    cursor.execute("UPDATE users SET streak_count = ?, last_active_date = ? WHERE id = ?", 
                   (streak, today_str if streak > 0 else '', user_id))
    conn.commit()
    conn.close()
    return streak

def log_daily_user_checkin(user_id):
    """Logs daily check-in activity for the user to maintain consecutive streak."""
    now_dt = datetime.now()
    today_str = now_dt.strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM user_study_activity WHERE user_id = ? AND activity_date = ? AND activity_type = 'check_in'",
        (user_id, today_str)
    )
    existing = cursor.fetchone()
    conn.close()

    if not existing:
        log_study_activity(user_id, "check_in", points=1, details="Daily Streak Check-in", activity_date=today_str)

    return calculate_user_streak(user_id)

def get_user_full_profile(user_id):
    """Retrieves full profile with streak, heatmap, completed courses, academics, and applications."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, email, name, role, avatar_emoji, avatar_url, banner_color, banner_url, banner_fit, banner_aspect, bio, target_role,
               streak_count, last_active_date, college_name, grad_year,
               github_handle, leetcode_handle, linkedin_url, portfolio_url, twitter_handle, skills,
               questions_solved_total, created_at
        FROM users WHERE id = ?
    """, (user_id,))
    user_row = cursor.fetchone()
    conn.close()
    if not user_row:
        return None
    user_data = dict(user_row)

    # Dynamic streak calculation from real consecutive activity days
    calculated_streak = calculate_user_streak(user_id)
    
    completed_courses = get_user_completed_courses(user_id)
    applied_events = get_user_applied_events(user_id)
    heatmap = get_user_study_heatmap(user_id)

    user_data["completed_courses"] = completed_courses
    user_data["completed_course_ids"] = [c["id"] for c in completed_courses]
    user_data["applied_events"] = applied_events
    user_data["applied_event_ids"] = [e["id"] for e in applied_events]
    user_data["heatmap"] = heatmap
    user_data["full_name"] = user_data.get("name") or ""
    user_data["streak_count"] = calculated_streak
    user_data["daily_streak"] = calculated_streak
    user_data["avatar_url"] = user_data.get("avatar_url") or ""
    user_data["portfolio_url"] = user_data.get("portfolio_url") or ""
    user_data["twitter_handle"] = user_data.get("twitter_handle") or ""
    user_data["skills"] = user_data.get("skills") or "Python, JavaScript, React, DSA, SQL, Git"
    user_data["banner_url"] = user_data.get("banner_url") or ""
    user_data["banner_fit"] = user_data.get("banner_fit") or "cover"
    user_data["banner_aspect"] = user_data.get("banner_aspect") or "wide"
    user_data["banner_style"] = user_data.get("banner_color") or "gradient-purple"
    return user_data

def update_user_profile(user_id, data):
    """Updates user details, academics, coding handles, emoji avatar, photo avatar, social links, and skills."""
    data_dict = dict(data)
    if "full_name" in data_dict and "name" not in data_dict:
        data_dict["name"] = data_dict["full_name"]
    if "daily_streak" in data_dict and "streak_count" not in data_dict:
        data_dict["streak_count"] = data_dict["daily_streak"]
    if "banner_style" in data_dict and "banner_color" not in data_dict:
        data_dict["banner_color"] = data_dict["banner_style"]

    conn = get_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    text_fields = (
        "name", "avatar_emoji", "avatar_url", "banner_color", "banner_url", "banner_fit", "banner_aspect",
        "bio", "target_role", "college_name", "grad_year", "github_handle", "leetcode_handle", "linkedin_url",
        "portfolio_url", "twitter_handle", "skills"
    )
    for field in text_fields:
        if field in data_dict and data_dict[field] is not None:
            updates.append(f"{field} = ?")
            params.append(str(data_dict[field]).strip())

    for int_field in ("streak_count", "questions_solved_total"):
        if int_field in data_dict and data_dict[int_field] is not None:
            updates.append(f"{int_field} = ?")
            params.append(int(data_dict[int_field]))

    if updates:
        params.append(user_id)
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    conn.close()
    return get_user_full_profile(user_id)

# ------------------ User DSA Streak & Problem Progress ------------------

def toggle_user_dsa_problem(user_id, problem_id, status='solved', topic=''):
    """Toggles solved or revision bookmark for a DSA problem."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT problem_id FROM user_dsa_progress WHERE user_id = ? AND problem_id = ? AND status = ?",
        (user_id, problem_id, status)
    )
    row = cursor.fetchone()
    now_iso = datetime.now(timezone.utc).isoformat()
    if row:
        cursor.execute(
            "DELETE FROM user_dsa_progress WHERE user_id = ? AND problem_id = ? AND status = ?",
            (user_id, problem_id, status)
        )
        active = False
    else:
        cursor.execute("""
            INSERT INTO user_dsa_progress (user_id, problem_id, status, marked_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, problem_id, status, now_iso))
        active = True
    conn.commit()
    conn.close()

    if status == 'solved' and active:
        # Increment questions solved count and study heatmap
        log_user_questions_solved(user_id, count=1, topic=topic or f"Solved DSA: {problem_id}")

    return active

def get_user_dsa_progress(user_id):
    """Returns lists of solved and revision problem IDs for the user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT problem_id, status FROM user_dsa_progress WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    
    solved = [r["problem_id"] for r in rows if r["status"] == 'solved']
    revision = [r["problem_id"] for r in rows if r["status"] == 'revision']
    return {"solved": solved, "revision": revision}


# ------------------ Notifications Management ------------------

def create_notification(title, message, link_url='#', n_type='announcement', user_id=None):
    """Creates a new broadcast (user_id=None) or targeted notification."""
    conn = get_connection()
    cursor = conn.cursor()
    n_id = f"notif_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:6]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        INSERT INTO notifications (id, user_id, title, message, type, link_url, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (n_id, user_id, title.strip(), message.strip(), n_type, (link_url or '#').strip(), now_iso))
    conn.commit()
    conn.close()
    return n_id

def get_notifications_for_user(user_id=None, limit=25):
    """Fetches notifications applicable to the user and calculates unread count."""
    conn = get_connection()
    cursor = conn.cursor()

    # Seed welcome notification if none exist
    cursor.execute("SELECT COUNT(*) FROM notifications")
    if cursor.fetchone()[0] == 0:
        now_iso = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            INSERT INTO notifications (id, user_id, title, message, type, link_url, created_at)
            VALUES 
            ('notif_init_1', NULL, '🚀 Welcome to Devengers v2026', 'Explore developer profiles, coding practice heatmaps, and official certificates.', 'announcement', 'events.html', ?),
            ('notif_init_2', NULL, '🏆 Certificate Verification Studio', 'Real-time credentials lookup and high-DPI export are live in Certificates.', 'system', 'certificates.html', ?)
        """, (now_iso, now_iso))
        conn.commit()

    if user_id:
        cursor.execute("""
            SELECT n.id, n.user_id, n.title, n.message, n.type, n.link_url, n.created_at,
                   CASE WHEN r.read_at IS NOT NULL THEN 1 ELSE 0 END as is_read
            FROM notifications n
            LEFT JOIN notification_reads r ON n.id = r.notification_id AND r.user_id = ?
            WHERE n.user_id IS NULL OR n.user_id = ?
            ORDER BY n.created_at DESC
            LIMIT ?
        """, (user_id, user_id, limit))
    else:
        cursor.execute("""
            SELECT id, user_id, title, message, type, link_url, created_at, 0 as is_read
            FROM notifications
            WHERE user_id IS NULL
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

    rows = cursor.fetchall()
    notifications = []
    unread_count = 0
    for r in rows:
        is_read = bool(r['is_read']) if 'is_read' in r.keys() else False
        if not is_read:
            unread_count += 1
        notifications.append({
            "id": r['id'],
            "user_id": r['user_id'],
            "title": r['title'],
            "message": r['message'],
            "type": r['type'],
            "link_url": r['link_url'],
            "created_at": r['created_at'],
            "is_read": is_read
        })
    conn.close()
    return notifications, unread_count

def mark_notifications_read(user_id, notification_ids=None):
    """Marks notifications as read for the user."""
    if not user_id:
        return
    conn = get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    if notification_ids:
        for nid in notification_ids:
            cursor.execute("""
                INSERT OR IGNORE INTO notification_reads (user_id, notification_id, read_at)
                VALUES (?, ?, ?)
            """, (user_id, nid, now_iso))
    else:
        cursor.execute("""
            SELECT id FROM notifications WHERE user_id IS NULL OR user_id = ?
        """, (user_id,))
        rows = cursor.fetchall()
        for r in rows:
            cursor.execute("""
                INSERT OR IGNORE INTO notification_reads (user_id, notification_id, read_at)
                VALUES (?, ?, ?)
            """, (user_id, r['id'], now_iso))

    conn.commit()
    conn.close()

def get_all_broadcast_notifications(limit=50):
    """Fetches all pushed broadcast notifications for administration."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.id, n.title, n.message, n.type, n.link_url, n.created_at,
               (SELECT COUNT(*) FROM notification_reads r WHERE r.notification_id = n.id) as read_count
        FROM notifications n
        WHERE n.user_id IS NULL
        ORDER BY n.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "title": r["title"],
            "message": r["message"],
            "type": r["type"],
            "link_url": r["link_url"],
            "created_at": r["created_at"],
            "read_count": r["read_count"]
        })
    conn.close()
    return items

def delete_notification(notification_id):
    """Deletes a notification and cascades read records."""
    if not notification_id:
        return False
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notification_reads WHERE notification_id = ?", (notification_id,))
    cursor.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


