"""
Devengers Gallery & Community Projects Service.
Handles:
1. Latest Opportunity Posters (Advertising panel with auto horizontal animation)
2. Our Previous Events (Admin manageable with croppable thumbnail & live preview)
3. Community Projects (Uploaded & managed by logged-in users, moderated by admin, interactive Q&A discussion chats)
Zero external dependencies.
"""

import sqlite3
import os
import uuid
from datetime import datetime, timezone

SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SERVICE_DIR, "devengers.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_gallery_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Gallery Posters (Latest Opportunities Banner)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gallery_posters (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            subtitle TEXT,
            image_url TEXT NOT NULL,
            link_url TEXT,
            badge_text TEXT DEFAULT 'HOT',
            order_index INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 2. Previous Events (Replaces "On the Web")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS previous_events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            organization TEXT NOT NULL,
            thumbnail TEXT NOT NULL,
            event_date TEXT,
            category TEXT DEFAULT 'Hackathon',
            link_url TEXT,
            order_index INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 3. Community Projects (Publicly browseable, uploaded by logged-in users, deletable by admin)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS community_projects (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            tagline TEXT,
            description TEXT NOT NULL,
            tech_stack TEXT DEFAULT '',
            thumbnail TEXT NOT NULL,
            demo_url TEXT,
            video_url TEXT,
            github_url TEXT,
            category TEXT DEFAULT 'Web & App',
            likes_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 4. Project Comments / Q&A Discussion Chats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_comments (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            parent_id TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES community_projects(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posters_order ON gallery_posters(order_index);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_prev_events_order ON previous_events(order_index);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_comm_proj_user ON community_projects(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_comments ON project_comments(project_id);")

    conn.commit()
    conn.close()

    seed_gallery_defaults_if_empty()

def seed_gallery_defaults_if_empty():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Seed Posters if empty
    cursor.execute("SELECT COUNT(*) AS cnt FROM gallery_posters")
    if cursor.fetchone()["cnt"] == 0:
        now = datetime.now(timezone.utc).isoformat()
        starter_posters = [
            (
                "poster_1",
                "Devengers National Hackathon 2026",
                "₹1,50,000 Prize Pool • 36h Code Sprint • Mentors from Top Tech",
                "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?q=80&w=1200&auto=format&fit=crop",
                "events.html",
                "FEATURED",
                1,
                1,
                now,
                now
            ),
            (
                "poster_2",
                "Summer SDE & AI Internship Drive",
                "Direct Interviews with 40+ Product Companies & Funded Startups",
                "https://images.unsplash.com/photo-1522071820081-009f0129c71c?q=80&w=1200&auto=format&fit=crop",
                "jobs.html",
                "HIRING NOW",
                2,
                1,
                now,
                now
            ),
            (
                "poster_3",
                "100 Days of DSA & System Design",
                "Daily Curated Problems, LeetCode Streaks & Live Leaderboard",
                "https://images.unsplash.com/photo-1555066931-4365d14bab8c?q=80&w=1200&auto=format&fit=crop",
                "dsa.html",
                "STREAK LIVE",
                3,
                1,
                now,
                now
            ),
            (
                "poster_4",
                "Global Open Source & AI Fellowship",
                "Contribute to High-Impact Repositories & Win Global Developer Grants",
                "https://images.unsplash.com/photo-1517245386807-bb43f82c33c4?q=80&w=1200&auto=format&fit=crop",
                "campus.html",
                "APPLY NOW",
                4,
                1,
                now,
                now
            )
        ]
        cursor.executemany("""
            INSERT INTO gallery_posters (id, title, subtitle, image_url, link_url, badge_text, order_index, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, starter_posters)

    # 2. Seed Previous Events if empty
    cursor.execute("SELECT COUNT(*) AS cnt FROM previous_events")
    if cursor.fetchone()["cnt"] == 0:
        now = datetime.now(timezone.utc).isoformat()
        starter_events = [
            (
                "prev_evt_1",
                "DevCon Global Hackfest 2025",
                "Google Developer Groups & Devengers",
                "https://images.unsplash.com/photo-1515187029135-18ee286d815b?q=80&w=800&auto=format&fit=crop",
                "Nov 2025",
                "Hackathon",
                "events.html",
                1,
                now,
                now
            ),
            (
                "prev_evt_2",
                "Winter Code Blitz 2.0",
                "Polygon Guild & TechNext",
                "https://images.unsplash.com/photo-1531482615713-2afd69097998?q=80&w=800&auto=format&fit=crop",
                "Dec 2025",
                "Coding Sprint",
                "events.html",
                2,
                now,
                now
            ),
            (
                "prev_evt_3",
                "Open Source AI Innovation Summit",
                "Devengers Core Foundation",
                "https://images.unsplash.com/photo-1528605248644-14dd04022da1?q=80&w=800&auto=format&fit=crop",
                "Jan 2026",
                "Tech Summit",
                "events.html",
                3,
                now,
                now
            ),
            (
                "prev_evt_4",
                "Algorithmic Masterclass & Hiring Expo",
                "Amazon & Microsoft Mentors x Devengers",
                "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?q=80&w=800&auto=format&fit=crop",
                "Feb 2026",
                "Masterclass",
                "events.html",
                4,
                now,
                now
            )
        ]
        cursor.executemany("""
            INSERT INTO previous_events (id, title, organization, thumbnail, event_date, category, link_url, order_index, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, starter_events)

    # 3. Seed Starter Community Projects if empty
    cursor.execute("SELECT COUNT(*) AS cnt FROM community_projects")
    if cursor.fetchone()["cnt"] == 0:
        # Get admin user ID for authoring seed projects
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin = cursor.fetchone()
        if not admin:
            cursor.execute("SELECT id FROM users LIMIT 1")
            admin = cursor.fetchone()
        admin_id = admin["id"] if admin else None

        if not admin_id:
            conn.close()
            return

        now = datetime.now(timezone.utc).isoformat()
        starter_projects = [
            (
                "proj_1",
                admin_id,
                "KODE Immersive 3D Engine",
                "Next-gen WebGL interactive spatial computing engine for developer portfolios.",
                "KODE Immersive is a high-performance WebGL sandbox built with Three.js and WebGPU shaders. Enables creators to visualize complex architectures in real-time 3D spaces with zero lag.",
                "Three.js, WebGPU, TypeScript, Vite, TailwindCSS",
                "https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=800&auto=format&fit=crop",
                "https://github.com",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://github.com",
                "Web & 3D",
                24,
                now,
                now
            ),
            (
                "proj_2",
                admin_id,
                "Ascension Cloud Orchestrator",
                "Serverless microservices deployment pipeline with automated rollback and canary testing.",
                "Ascension provides autonomous canary analysis, real-time metrics telemetry, and automated Kubernetes traffic routing for modern engineering teams.",
                "Go, Docker, Kubernetes, Prometheus, React",
                "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=800&auto=format&fit=crop",
                "https://github.com",
                "",
                "https://github.com",
                "DevOps & Cloud",
                19,
                now,
                now
            ),
            (
                "proj_3",
                admin_id,
                "Allies AI Pair Programmer",
                "Context-aware neural coding assistant optimized for competitive programming and DSA.",
                "Allies uses deep AST parsing to detect code smells, optimize time complexity from O(N^2) to O(N log N), and explain edge-case bugs in simple English.",
                "Python, FastAPI, Transformers, PyTorch, Next.js",
                "https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=80&w=800&auto=format&fit=crop",
                "https://github.com",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://github.com",
                "AI / ML",
                37,
                now,
                now
            ),
            (
                "proj_4",
                admin_id,
                "Super Evil Genius Corp Web Suite",
                "Cyberpunk brutalist portfolio framework designed for unconventional digital artists.",
                "A modular frontend showcase emphasizing hyper-kinetic typography, brutalist box-shadows, audio-reactive micro-interactions, and accessible keyboard navigation.",
                "Vanilla JS, Web Audio API, CSS Custom Properties, Canvas",
                "https://images.unsplash.com/photo-1544256718-3b621d15024c?q=80&w=800&auto=format&fit=crop",
                "https://github.com",
                "",
                "https://github.com",
                "Design & UI",
                14,
                now,
                now
            ),
            (
                "proj_5",
                admin_id,
                "Money in Check — FinTech Tracker",
                "Privacy-first decentralized expense tracking and crypto portfolio dashboard.",
                "Zero third-party tracking. All financial records are encrypted client-side using WebCrypto AES-GCM and synchronized via encrypted peer-to-peer WebRTC channels.",
                "React, IndexedDB, WebCrypto, TailwindCSS, Chart.js",
                "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?q=80&w=800&auto=format&fit=crop",
                "https://github.com",
                "",
                "https://github.com",
                "FinTech",
                28,
                now,
                now
            ),
            (
                "proj_6",
                admin_id,
                "Cloudstudio Realtime IDE",
                "Collaborative in-browser code editor with terminal emulation and instant container execution.",
                "Cloudstudio turns your browser into a full Linux workstation. Supports simultaneous multi-cursor pairing, video huddles, and sub-10ms keystroke synchronization.",
                "Node.js, WebSockets, xterm.js, Monaco Editor, Rust",
                "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=800&auto=format&fit=crop",
                "https://github.com",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://github.com",
                "Developer Tools",
                42,
                now,
                now
            )
        ]

        cursor.executemany("""
            INSERT INTO community_projects (id, user_id, title, tagline, description, tech_stack, thumbnail, demo_url, video_url, github_url, category, likes_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, starter_projects)

        # Seed sample starter questions & answers
        starter_comments = [
            (
                "comm_1",
                "proj_1",
                admin_id,
                None,
                "Hey everyone! Welcome to KODE Immersive. Feel free to ask any questions about WebGPU shader pipeline or performance tuning!",
                now
            ),
            (
                "comm_2",
                "proj_3",
                admin_id,
                None,
                "Does Allies support custom AST rules for competitive programming platforms like Codeforces?",
                now
            ),
            (
                "comm_3",
                "proj_3",
                admin_id,
                "comm_2",
                "Yes! We have custom scrapers and problem parser plugins for both Codeforces and LeetCode.",
                now
            )
        ]
        cursor.executemany("""
            INSERT INTO project_comments (id, project_id, user_id, parent_id, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, starter_comments)

    conn.commit()
    conn.close()

# =========================================================================
# 1. Posters (Advertising Carousel) CRUD
# =========================================================================

def get_posters(only_active=False):
    conn = get_connection()
    cursor = conn.cursor()
    if only_active:
        cursor.execute("SELECT * FROM gallery_posters WHERE is_active = 1 ORDER BY order_index ASC, created_at DESC")
    else:
        cursor.execute("SELECT * FROM gallery_posters ORDER BY order_index ASC, created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_poster(poster_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gallery_posters WHERE id = ?", (poster_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_poster(data):
    poster_id = f"poster_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO gallery_posters (id, title, subtitle, image_url, link_url, badge_text, order_index, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        poster_id,
        data.get("title", "").strip() or "New Opportunity",
        data.get("subtitle", "").strip() or "",
        data.get("image_url", "").strip(),
        data.get("link_url", "").strip() or "#",
        data.get("badge_text", "OPPORTUNITY").strip(),
        int(data.get("order_index", 0) or 0),
        1 if data.get("is_active", True) else 0,
        now,
        now
    ))
    conn.commit()
    conn.close()
    return get_poster(poster_id)

def update_poster(poster_id, data):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE gallery_posters
        SET title = ?, subtitle = ?, image_url = ?, link_url = ?, badge_text = ?, order_index = ?, is_active = ?, updated_at = ?
        WHERE id = ?
    """, (
        data.get("title", "").strip(),
        data.get("subtitle", "").strip(),
        data.get("image_url", "").strip(),
        data.get("link_url", "").strip(),
        data.get("badge_text", "OPPORTUNITY").strip(),
        int(data.get("order_index", 0) or 0),
        1 if data.get("is_active", True) else 0,
        now,
        poster_id
    ))
    conn.commit()
    conn.close()
    return get_poster(poster_id)

def delete_poster(poster_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gallery_posters WHERE id = ?", (poster_id,))
    conn.commit()
    conn.close()
    return True

# =========================================================================
# 2. Previous Events CRUD
# =========================================================================

def get_previous_events():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM previous_events ORDER BY order_index ASC, created_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_previous_event(event_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM previous_events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_previous_event(data):
    event_id = f"prev_evt_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO previous_events (id, title, organization, thumbnail, event_date, category, link_url, order_index, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        event_id,
        data.get("title", "").strip() or "Untitled Event",
        data.get("organization", "").strip() or "Devengers Community",
        data.get("thumbnail", "").strip(),
        data.get("event_date", "").strip() or "",
        data.get("category", "Hackathon").strip(),
        data.get("link_url", "").strip() or "#",
        int(data.get("order_index", 0) or 0),
        now,
        now
    ))
    conn.commit()
    conn.close()
    return get_previous_event(event_id)

def update_previous_event(event_id, data):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE previous_events
        SET title = ?, organization = ?, thumbnail = ?, event_date = ?, category = ?, link_url = ?, order_index = ?, updated_at = ?
        WHERE id = ?
    """, (
        data.get("title", "").strip(),
        data.get("organization", "").strip(),
        data.get("thumbnail", "").strip(),
        data.get("event_date", "").strip(),
        data.get("category", "Hackathon").strip(),
        data.get("link_url", "").strip(),
        int(data.get("order_index", 0) or 0),
        now,
        event_id
    ))
    conn.commit()
    conn.close()
    return get_previous_event(event_id)

def delete_previous_event(event_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM previous_events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    return True

# =========================================================================
# 3. Community Projects CRUD
# =========================================================================

def get_community_projects(search=None, category=None):
    conn = get_connection()
    cursor = conn.cursor()
    sql = """
        SELECT cp.*,
               u.name AS author_name,
               u.email AS author_email,
               u.avatar_emoji AS author_emoji,
               u.avatar_url AS author_avatar,
               u.role AS author_role,
               (SELECT COUNT(*) FROM project_comments pc WHERE pc.project_id = cp.id) AS comments_count
        FROM community_projects cp
        LEFT JOIN users u ON cp.user_id = u.id
        WHERE 1=1
    """
    params = []
    if search:
        s = f"%{search.strip()}%"
        sql += " AND (cp.title LIKE ? OR cp.tagline LIKE ? OR cp.description LIKE ? OR cp.tech_stack LIKE ?)"
        params.extend([s, s, s, s])
    if category and category != 'All':
        sql += " AND cp.category = ?"
        params.append(category)

    sql += " ORDER BY cp.created_at DESC"
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_community_project(project_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT cp.*,
               u.name AS author_name,
               u.email AS author_email,
               u.avatar_emoji AS author_emoji,
               u.avatar_url AS author_avatar,
               u.role AS author_role,
               (SELECT COUNT(*) FROM project_comments pc WHERE pc.project_id = cp.id) AS comments_count
        FROM community_projects cp
        LEFT JOIN users u ON cp.user_id = u.id
        WHERE cp.id = ?
    """, (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_community_project(user_id, data):
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO community_projects (
            id, user_id, title, tagline, description, tech_stack,
            thumbnail, demo_url, video_url, github_url, category, likes_count,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
    """, (
        project_id,
        user_id,
        data.get("title", "").strip() or "Untitled Project",
        data.get("tagline", "").strip() or "",
        data.get("description", "").strip(),
        data.get("tech_stack", "").strip(),
        data.get("thumbnail", "").strip(),
        data.get("demo_url", "").strip(),
        data.get("video_url", "").strip(),
        data.get("github_url", "").strip(),
        data.get("category", "Web & App").strip(),
        now,
        now
    ))
    conn.commit()
    conn.close()
    return get_community_project(project_id)

def update_community_project(project_id, user_id, is_admin, data):
    proj = get_community_project(project_id)
    if not proj:
        return None, "Project not found"
    if proj["user_id"] != user_id and not is_admin:
        return None, "Unauthorized to edit this project"

    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE community_projects
        SET title = ?, tagline = ?, description = ?, tech_stack = ?,
            thumbnail = ?, demo_url = ?, video_url = ?, github_url = ?,
            category = ?, updated_at = ?
        WHERE id = ?
    """, (
        data.get("title", proj["title"]).strip(),
        data.get("tagline", proj["tagline"]).strip(),
        data.get("description", proj["description"]).strip(),
        data.get("tech_stack", proj["tech_stack"]).strip(),
        data.get("thumbnail", proj["thumbnail"]).strip(),
        data.get("demo_url", proj["demo_url"]).strip(),
        data.get("video_url", proj["video_url"]).strip(),
        data.get("github_url", proj["github_url"]).strip(),
        data.get("category", proj["category"]).strip(),
        now,
        project_id
    ))
    conn.commit()
    conn.close()
    return get_community_project(project_id), None

def delete_community_project(project_id, user_id, is_admin):
    proj = get_community_project(project_id)
    if not proj:
        return False, "Project not found"
    # Admin can delete any project, user can delete their own project
    if proj["user_id"] != user_id and not is_admin:
        return False, "Unauthorized to delete this project"

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM community_projects WHERE id = ?", (project_id,))
    cursor.execute("DELETE FROM project_comments WHERE project_id = ?", (project_id,))
    conn.commit()
    conn.close()
    return True, None

def get_user_projects(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT cp.*,
               (SELECT COUNT(*) FROM project_comments pc WHERE pc.project_id = cp.id) AS comments_count
        FROM community_projects cp
        WHERE cp.user_id = ?
        ORDER BY cp.created_at DESC
    """, (user_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# =========================================================================
# 4. Project Comments / Q&A Discussion Chats CRUD
# =========================================================================

def get_project_comments(project_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pc.*,
               u.name AS author_name,
               u.email AS author_email,
               u.avatar_emoji AS author_emoji,
               u.avatar_url AS author_avatar,
               u.role AS author_role
        FROM project_comments pc
        LEFT JOIN users u ON pc.user_id = u.id
        WHERE pc.project_id = ?
        ORDER BY pc.created_at ASC
    """, (project_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def add_project_comment(project_id, user_id, parent_id, message):
    if not message or not message.strip():
        return None, "Comment message cannot be empty"
    comment_id = f"comm_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO project_comments (id, project_id, user_id, parent_id, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        comment_id,
        project_id,
        user_id,
        parent_id if parent_id else None,
        message.strip(),
        now
    ))
    conn.commit()
    conn.close()

    # Fetch new comment with author info
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pc.*,
               u.name AS author_name,
               u.email AS author_email,
               u.avatar_emoji AS author_emoji,
               u.avatar_url AS author_avatar,
               u.role AS author_role
        FROM project_comments pc
        LEFT JOIN users u ON pc.user_id = u.id
        WHERE pc.id = ?
    """, (comment_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None, None

def delete_project_comment(comment_id, user_id, is_admin):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM project_comments WHERE id = ?", (comment_id,))
    comm = cursor.fetchone()
    if not comm:
        conn.close()
        return False, "Comment not found"
    if comm["user_id"] != user_id and not is_admin:
        conn.close()
        return False, "Unauthorized to delete this comment"

    cursor.execute("DELETE FROM project_comments WHERE id = ? OR parent_id = ?", (comment_id, comment_id))
    conn.commit()
    conn.close()
    return True, None
