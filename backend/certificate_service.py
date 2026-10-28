"""
Devengers Certificate Management Service.
Handles competition certificate configuration, visual name anchor tags,
Excel/CSV participant roster parsing, real-time participant lookup,
issue reporting, and high-resolution rendering metadata.
Zero external dependencies - powered by Python's standard library and SQLite.
"""

import os
import io
import re
import csv
import json
import uuid
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import db

def init_certificate_tables():
    """Initializes tables for certificate competitions, participants, and issues."""
    conn = db.get_connection()
    cursor = conn.cursor()

    # Competitions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certificates_competitions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            certificate_type TEXT DEFAULT 'Certificate of Excellence',
            issue_date TEXT,
            description TEXT,
            template_url TEXT NOT NULL,
            template_width INTEGER DEFAULT 1920,
            template_height INTEGER DEFAULT 1080,
            name_x REAL DEFAULT 50.0,
            name_y REAL DEFAULT 50.0,
            name_font TEXT DEFAULT 'Playfair Display',
            name_size INTEGER DEFAULT 58,
            name_color TEXT DEFAULT '#FFD700',
            name_align TEXT DEFAULT 'center',
            name_case TEXT DEFAULT 'capitalize',
            name_weight TEXT DEFAULT 'bold',
            show_cert_id INTEGER DEFAULT 1,
            cert_id_x REAL DEFAULT 82.0,
            cert_id_y REAL DEFAULT 88.0,
            show_date INTEGER DEFAULT 1,
            date_x REAL DEFAULT 34.0,
            date_y REAL DEFAULT 78.0,
            status TEXT DEFAULT 'Published' CHECK(status IN ('Draft', 'Published', 'Archived')),
            created_by TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Participants Roster Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certificate_participants (
            id TEXT PRIMARY KEY,
            competition_id TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT COLLATE NOCASE,
            role_or_rank TEXT DEFAULT 'Participant',
            certificate_number TEXT UNIQUE NOT NULL,
            issued_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (competition_id) REFERENCES certificates_competitions(id) ON DELETE CASCADE
        )
    """)

    # Indices for blazing fast lookup by name or email
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cert_comp_email ON certificate_participants(competition_id, email);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cert_comp_name ON certificate_participants(competition_id, name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cert_number ON certificate_participants(certificate_number);")

    # Issue Reporting Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certificate_issues (
            id TEXT PRIMARY KEY,
            competition_id TEXT,
            competition_title TEXT,
            participant_name TEXT,
            participant_email TEXT,
            issue_type TEXT NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'Open',
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def seed_starter_certificates_if_empty(admin_id=None):
    """Seeds default luxury competitions and demo participants if none exist."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS cnt FROM certificates_competitions")
    row = cursor.fetchone()
    if row and row["cnt"] > 0:
        conn.close()
        return

    now = datetime.now(timezone.utc).isoformat()
    c1_id = "comp_dev_hack_2026"
    c2_id = "comp_dsa_sprint_2026"

    # Competition 1: Devengers National Hackathon 2026
    cursor.execute("""
        INSERT INTO certificates_competitions (
            id, title, certificate_type, issue_date, description,
            template_url, template_width, template_height,
            name_x, name_y, name_font, name_size, name_color, name_align, name_case, name_weight,
            show_cert_id, cert_id_x, cert_id_y, show_date, date_x, date_y,
            status, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        c1_id,
        "Devengers National Hackathon 2026",
        "Certificate of Excellence",
        "October 20, 2026",
        "Flagship 36-hour national engineering hackathon organized by DEVENGERS.",
        "Assest/uploads/cert_template_gold_luxury.jpg",
        1920, 1080,
        50.0, 48.0, "Playfair Display", 58, "#F7D070", "center", "capitalize", "bold",
        1, 80.0, 86.0, 1, 35.0, 77.0,
        "Published", admin_id, now, now
    ))

    # Competition 2: National DSA & Algorithmic Code Sprint
    cursor.execute("""
        INSERT INTO certificates_competitions (
            id, title, certificate_type, issue_date, description,
            template_url, template_width, template_height,
            name_x, name_y, name_font, name_size, name_color, name_align, name_case, name_weight,
            show_cert_id, cert_id_x, cert_id_y, show_date, date_x, date_y,
            status, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        c2_id,
        "National DSA & Algorithmic Code Sprint",
        "Certificate of Participation",
        "October 15, 2026",
        "Intense 3-hour competitive programming & algorithmic problem solving challenge.",
        "Assest/uploads/cert_template_achievement.jpg",
        1920, 1080,
        50.0, 51.5, "Cinzel", 52, "#F7D070", "center", "capitalize", "bold",
        1, 80.0, 86.0, 1, 36.5, 77.5,
        "Published", admin_id, now, now
    ))

    # Seed participants for testing immediate real-time search & download
    demo_roster = [
        (c1_id, "Kishan Kumar", "kishan@devengers.org", "Winner - 1st Place", "DEV-2026-HACK-0001"),
        (c1_id, "Aarav Sharma", "aarav.sharma@example.com", "Finalist", "DEV-2026-HACK-0002"),
        (c1_id, "Ananya Verma", "ananya.v@example.com", "Special Merit", "DEV-2026-HACK-0003"),
        (c1_id, "Rohan Gupta", "rohan.gupta@example.com", "Participant", "DEV-2026-HACK-0004"),
        (c1_id, "Priya Nair", "priya.nair@example.com", "Participant", "DEV-2026-HACK-0005"),
        (c2_id, "Kishan Kumar", "kishan@devengers.org", "Top 1% Percentile", "DEV-2026-DSA-0101"),
        (c2_id, "Sneha Kulkarni", "sneha.k@example.com", "Top 5% Percentile", "DEV-2026-DSA-0102"),
        (c2_id, "Aditya Roy", "aditya.roy@example.com", "Participant", "DEV-2026-DSA-0103")
    ]

    for comp_id, name, email, rank, cert_no in demo_roster:
        cursor.execute("""
            INSERT INTO certificate_participants (
                id, competition_id, name, email, role_or_rank, certificate_number, issued_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (str(uuid.uuid4()), comp_id, name, email, rank, cert_no, "2026-10-20", now))

    conn.commit()
    conn.close()
    print("[Certificate Service] Initialized tables and seeded starter certificate competitions & participants.")


# ==========================================
# PUBLIC API: Search, Verification & Issues
# ==========================================

def get_public_competitions():
    """Returns active published competitions for the public certificate search dropdown/cards."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.title, c.certificate_type, c.issue_date, c.description, c.template_url,
               COUNT(p.id) as participant_count
        FROM certificates_competitions c
        LEFT JOIN certificate_participants p ON c.id = p.competition_id
        WHERE c.status = 'Published'
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """)
    rows = cursor.fetchall()
    competitions = [dict(r) for r in rows]
    conn.close()
    return competitions


def verify_and_fetch_certificate(competition_id, query_str):
    """
    Real-time backend check.
    Supports matching by email OR name (or both).
    Case-insensitive, whitespace-trimmed.
    """
    if not query_str or not competition_id:
        return {"found": False, "message": "Competition and Name or Email are required."}

    query = query_str.strip()
    conn = db.get_connection()
    cursor = conn.cursor()

    # 1. Fetch competition config
    cursor.execute("SELECT * FROM certificates_competitions WHERE id = ? AND status = 'Published'", (competition_id,))
    comp_row = cursor.fetchone()
    if not comp_row:
        conn.close()
        return {"found": False, "message": "Competition not found or certificate not currently published."}

    competition = dict(comp_row)

    # 2. Search participant: exact email -> exact name -> case-insensitive / partial
    participant = None

    # Check email exact match
    if "@" in query:
        cursor.execute("""
            SELECT * FROM certificate_participants 
            WHERE competition_id = ? AND LOWER(email) = LOWER(?)
            LIMIT 1
        """, (competition_id, query))
        p_row = cursor.fetchone()
        if p_row:
            participant = dict(p_row)

    # Check name exact match
    if not participant:
        cursor.execute("""
            SELECT * FROM certificate_participants 
            WHERE competition_id = ? AND LOWER(TRIM(name)) = LOWER(?)
            LIMIT 1
        """, (competition_id, query))
        p_row = cursor.fetchone()
        if p_row:
            participant = dict(p_row)

    # Check case-insensitive wildcard match on name OR email
    if not participant:
        like_term = f"%{query}%"
        cursor.execute("""
            SELECT * FROM certificate_participants 
            WHERE competition_id = ? AND (LOWER(name) LIKE LOWER(?) OR LOWER(email) LIKE LOWER(?))
            ORDER BY CASE WHEN LOWER(name) = LOWER(?) THEN 1 ELSE 2 END
            LIMIT 1
        """, (competition_id, like_term, like_term, query))
        p_row = cursor.fetchone()
        if p_row:
            participant = dict(p_row)

    conn.close()

    if not participant:
        return {
            "found": False,
            "message": f"No eligible participant record found for '{query}'. Please check spelling or verify your registered email."
        }

    return {
        "found": True,
        "participant": participant,
        "competition": competition
    }


def get_user_certificates(email):
    """Fetches all verified certificates awarded to a user's email address."""
    if not email:
        return []
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.competition_id, p.name, p.email, p.role_or_rank, p.certificate_number, p.issued_at,
               c.title, c.certificate_type, c.issue_date, c.template_url,
               c.name_x, c.name_y, c.name_font, c.name_size, c.name_color, c.name_align, c.name_case, c.name_weight,
               c.show_cert_id, c.cert_id_x, c.cert_id_y, c.show_date, c.date_x, c.date_y
        FROM certificate_participants p
        JOIN certificates_competitions c ON p.competition_id = c.id
        WHERE p.email = ? COLLATE NOCASE
        ORDER BY p.created_at DESC
    """, (email.strip(),))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "competition_id": r[1],
            "name": r[2],
            "email": r[3],
            "role_or_rank": r[4],
            "certificate_number": r[5],
            "issued_at": r[6] or r[9],
            "competition_title": r[7],
            "certificate_type": r[8],
            "template_url": r[10],
            "rendering": {
                "name_x": r[11],
                "name_y": r[12],
                "name_font": r[13],
                "name_size": r[14],
                "name_color": r[15],
                "name_align": r[16],
                "name_case": r[17],
                "name_weight": r[18],
                "show_cert_id": bool(r[19]),
                "cert_id_x": r[20],
                "cert_id_y": r[21],
                "show_date": bool(r[22]),
                "date_x": r[23],
                "date_y": r[24]
            }
        })
    return results


def report_certificate_issue(data):
    """Stores an issue/discrepancy reported by a participant."""
    conn = db.get_connection()
    cursor = conn.cursor()
    issue_id = f"ISSUE-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now(timezone.utc).isoformat()

    comp_id = data.get("competition_id", "")
    comp_title = data.get("competition_title", "")
    p_name = data.get("participant_name", "")
    p_email = data.get("participant_email", "")
    issue_type = data.get("issue_type", "Other")
    msg = data.get("message", "")

    cursor.execute("""
        INSERT INTO certificate_issues (
            id, competition_id, competition_title, participant_name, participant_email,
            issue_type, message, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Open', ?)
    """, (issue_id, comp_id, comp_title, p_name, p_email, issue_type, msg, now))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "issue_id": issue_id,
        "support_email": "support@devengers.org"
    }


# ==========================================
# ADMIN API: CRUD, Drag/Drop Anchors & Rosters
# ==========================================

def get_admin_competitions():
    """Lists all competitions with detailed statistics for admin dashboard."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, COUNT(p.id) AS participant_count
        FROM certificates_competitions c
        LEFT JOIN certificate_participants p ON c.id = p.competition_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """)
    rows = cursor.fetchall()
    competitions = [dict(r) for r in rows]
    conn.close()
    return competitions


def get_admin_competition(competition_id):
    """Fetches single competition configuration including coordinates."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM certificates_competitions WHERE id = ?", (competition_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    comp = dict(row)
    cursor.execute("SELECT COUNT(*) AS cnt FROM certificate_participants WHERE competition_id = ?", (competition_id,))
    comp["participant_count"] = cursor.fetchone()["cnt"]
    conn.close()
    return comp


def save_competition(data, user_id=None):
    """Creates or updates a certificate competition with template & anchor configs."""
    conn = db.get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    comp_id = data.get("id") or f"comp_{uuid.uuid4().hex[:10]}"
    title = data.get("title", "Untitled Competition")
    cert_type = data.get("certificate_type", "Certificate of Participation")
    issue_date = data.get("issue_date") or datetime.now().strftime("%B %d, %Y")
    desc = data.get("description", "")
    template_url = data.get("template_url") or "Assest/uploads/cert_template_gold_luxury.jpg"
    template_w = int(data.get("template_width") or 1920)
    template_h = int(data.get("template_height") or 1080)

    # Visual Anchor Configuration (Percentage coordinates)
    name_x = float(data.get("name_x", 50.0))
    name_y = float(data.get("name_y", 50.0))
    name_font = data.get("name_font", "Playfair Display")
    name_size = int(data.get("name_size", 56))
    name_color = data.get("name_color", "#FFD700")
    name_align = data.get("name_align", "center")
    name_case = data.get("name_case", "capitalize")
    name_weight = data.get("name_weight", "bold")

    show_cert_id = 1 if data.get("show_cert_id", True) else 0
    cert_id_x = float(data.get("cert_id_x", 82.0))
    cert_id_y = float(data.get("cert_id_y", 88.0))

    show_date = 1 if data.get("show_date", True) else 0
    date_x = float(data.get("date_x", 34.0))
    date_y = float(data.get("date_y", 78.0))

    status = data.get("status", "Published")

    cursor.execute("SELECT id FROM certificates_competitions WHERE id = ?", (comp_id,))
    exists = cursor.fetchone()

    if exists:
        cursor.execute("""
            UPDATE certificates_competitions SET
                title = ?, certificate_type = ?, issue_date = ?, description = ?,
                template_url = ?, template_width = ?, template_height = ?,
                name_x = ?, name_y = ?, name_font = ?, name_size = ?, name_color = ?,
                name_align = ?, name_case = ?, name_weight = ?,
                show_cert_id = ?, cert_id_x = ?, cert_id_y = ?,
                show_date = ?, date_x = ?, date_y = ?,
                status = ?, updated_at = ?
            WHERE id = ?
        """, (
            title, cert_type, issue_date, desc,
            template_url, template_w, template_h,
            name_x, name_y, name_font, name_size, name_color,
            name_align, name_case, name_weight,
            show_cert_id, cert_id_x, cert_id_y,
            show_date, date_x, date_y,
            status, now, comp_id
        ))
    else:
        cursor.execute("""
            INSERT INTO certificates_competitions (
                id, title, certificate_type, issue_date, description,
                template_url, template_width, template_height,
                name_x, name_y, name_font, name_size, name_color,
                name_align, name_case, name_weight,
                show_cert_id, cert_id_x, cert_id_y,
                show_date, date_x, date_y,
                status, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            comp_id, title, cert_type, issue_date, desc,
            template_url, template_w, template_h,
            name_x, name_y, name_font, name_size, name_color,
            name_align, name_case, name_weight,
            show_cert_id, cert_id_x, cert_id_y,
            show_date, date_x, date_y,
            status, user_id, now, now
        ))

    conn.commit()
    conn.close()
    return {"success": True, "id": comp_id}


def delete_competition(competition_id):
    """Deletes competition and all associated participants."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM certificates_competitions WHERE id = ?", (competition_id,))
    cursor.execute("DELETE FROM certificate_participants WHERE competition_id = ?", (competition_id,))
    conn.commit()
    conn.close()
    return {"success": True}


def get_competition_participants(competition_id, limit=500, offset=0):
    """Returns roster list for a competition."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM certificate_participants
        WHERE competition_id = ?
        ORDER BY created_at ASC
        LIMIT ? OFFSET ?
    """, (competition_id, limit, offset))
    rows = cursor.fetchall()
    participants = [dict(r) for r in rows]
    cursor.execute("SELECT COUNT(*) AS total FROM certificate_participants WHERE competition_id = ?", (competition_id,))
    total = cursor.fetchone()["total"]
    conn.close()
    return {"participants": participants, "total": total}


def get_all_issues():
    """Returns reported issues for admin review."""
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM certificate_issues ORDER BY created_at DESC LIMIT 100")
    rows = cursor.fetchall()
    issues = [dict(r) for r in rows]
    conn.close()
    return issues


# ==========================================
# EXCEL (.xlsx) & CSV NATIVE PARSER
# ==========================================

def parse_roster_file(file_bytes, filename=""):
    """
    Parses Excel (.xlsx) or CSV files using Python standard library.
    Zero external dependencies required.
    Returns list of {"name": str, "email": str, "role_or_rank": str}.
    """
    if not file_bytes:
        return []

    is_xlsx = False
    if filename.lower().endswith('.xlsx') or file_bytes.startswith(b'PK\x03\x04'):
        is_xlsx = True

    records = []
    if is_xlsx:
        records = _parse_xlsx_bytes(file_bytes)
    else:
        records = _parse_csv_bytes(file_bytes)

    # Clean and filter records
    valid_records = []
    for r in records:
        name = (r.get("name") or "").strip()
        email = (r.get("email") or "").strip()
        rank = (r.get("role_or_rank") or "Participant").strip()

        # If neither name nor email, skip
        if not name and not email:
            continue

        # If name is blank but email exists, infer name from email local-part
        if not name and email:
            name = email.split('@')[0].replace('.', ' ').replace('_', ' ').title()

        valid_records.append({
            "name": name,
            "email": email,
            "role_or_rank": rank
        })

    return valid_records


def _parse_csv_bytes(file_bytes):
    """Decodes and parses CSV bytes with delimiter detection."""
    text = ""
    for enc in ('utf-8', 'utf-8-sig', 'latin-1', 'cp1252'):
        try:
            text = file_bytes.decode(enc)
            break
        except Exception:
            continue

    if not text:
        return []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []

    # Detect delimiter
    sample = lines[0]
    delimiter = ','
    for d in (',', ';', '\t', '|'):
        if sample.count(d) > 0:
            delimiter = d
            break

    reader = csv.reader(lines, delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []

    # Analyze header
    header = [h.strip().lower() for h in rows[0]]
    name_col = -1
    email_col = -1
    rank_col = -1

    for idx, col in enumerate(header):
        c = col.replace(' ', '_').replace('-', '_')
        if any(k in c for k in ('participant_name', 'player_name', 'student_name', 'full_name', 'candidate_name', 'name', 'player')):
            if name_col == -1:
                name_col = idx
        elif any(k in c for k in ('email', 'e_mail', 'mail')):
            if email_col == -1:
                email_col = idx
        elif any(k in c for k in ('rank', 'position', 'role', 'status', 'award')):
            if rank_col == -1:
                rank_col = idx

    # If headers weren't found, try first row heuristic
    has_header = (name_col != -1 or email_col != -1)
    start_row = 1 if has_header else 0

    if not has_header:
        # Check first row values: which looks like email?
        for idx, val in enumerate(rows[0]):
            if '@' in val and '.' in val:
                email_col = idx
            elif len(val) > 1 and not val.isdigit() and name_col == -1:
                name_col = idx

    results = []
    for row in rows[start_row:]:
        if not row:
            continue
        name_val = row[name_col].strip() if 0 <= name_col < len(row) else ""
        email_val = row[email_col].strip() if 0 <= email_col < len(row) else ""
        rank_val = row[rank_col].strip() if 0 <= rank_col < len(row) else "Participant"

        # Heuristic fallback if columns weren't strict
        if not email_val:
            for c in row:
                if '@' in c and '.' in c:
                    email_val = c.strip()
                    break
        if not name_val:
            for c in row:
                if c != email_val and len(c.strip()) > 1 and not c.strip().isdigit():
                    name_val = c.strip()
                    break

        if name_val or email_val:
            results.append({
                "name": name_val,
                "email": email_val,
                "role_or_rank": rank_val or "Participant"
            })

    return results


def _parse_xlsx_bytes(file_bytes):
    """
    Parses an Office Open XML (.xlsx) workbook strictly via zipfile & ElementTree.
    Zero third-party pip packages required.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            # 1. Parse shared strings table (xl/sharedStrings.xml)
            shared_strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                ss_tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
                # Handle standard namespaces
                ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in ss_tree.findall('.//x:si', ns) or ss_tree.findall('.//{*}si'):
                    # Collect all text children
                    t_nodes = si.findall('.//x:t', ns) or si.findall('.//{*}t')
                    text = "".join(t.text or "" for t in t_nodes)
                    shared_strings.append(text)

            # 2. Parse sheet1 (xl/worksheets/sheet1.xml)
            sheet_name = 'xl/worksheets/sheet1.xml'
            if sheet_name not in z.namelist():
                # Pick first worksheet
                ws_names = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
                if not ws_names:
                    return []
                sheet_name = ws_names[0]

            ws_tree = ET.fromstring(z.read(sheet_name))
            ns = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

            rows_data = []
            rows_nodes = ws_tree.findall('.//x:row', ns) or ws_tree.findall('.//{*}row')

            for r_node in rows_nodes:
                row_cells = []
                c_nodes = r_node.findall('.//x:c', ns) or r_node.findall('.//{*}c')
                for c in c_nodes:
                    cell_type = c.get('t')
                    v_node = c.find('.//x:v', ns) or c.find('.//{*}v')
                    val = ""
                    if v_node is not None and v_node.text:
                        raw_v = v_node.text.strip()
                        if cell_type == 's':  # shared string index
                            try:
                                val = shared_strings[int(raw_v)]
                            except (IndexError, ValueError):
                                val = raw_v
                        else:
                            val = raw_v
                    row_cells.append(val)
                if any(row_cells):
                    rows_data.append(row_cells)

            if not rows_data:
                return []

            # Analyze header
            header = [h.strip().lower() for h in rows_data[0]]
            name_col = -1
            email_col = -1
            rank_col = -1

            for idx, col in enumerate(header):
                c = col.replace(' ', '_').replace('-', '_')
                if any(k in c for k in ('participant_name', 'player_name', 'student_name', 'full_name', 'candidate_name', 'name', 'player')):
                    if name_col == -1:
                        name_col = idx
                elif any(k in c for k in ('email', 'e_mail', 'mail')):
                    if email_col == -1:
                        email_col = idx
                elif any(k in c for k in ('rank', 'position', 'role', 'status', 'award')):
                    if rank_col == -1:
                        rank_col = idx

            has_header = (name_col != -1 or email_col != -1)
            start_idx = 1 if has_header else 0

            results = []
            for row in rows_data[start_idx:]:
                name_val = row[name_col].strip() if 0 <= name_col < len(row) else ""
                email_val = row[email_col].strip() if 0 <= email_col < len(row) else ""
                rank_val = row[rank_col].strip() if 0 <= rank_col < len(row) else "Participant"

                if not email_val:
                    for cell in row:
                        if '@' in cell and '.' in cell:
                            email_val = cell.strip()
                            break

                if not name_val:
                    for cell in row:
                        if cell != email_val and len(cell.strip()) > 1 and not cell.strip().isdigit():
                            name_val = cell.strip()
                            break

                if name_val or email_val:
                    results.append({
                        "name": name_val,
                        "email": email_val,
                        "role_or_rank": rank_val or "Participant"
                    })

            return results
    except Exception as e:
        print(f"[XLSX Parse Error] {e}")
        return []


def import_participants_bulk(competition_id, records, replace_existing=False):
    """Inserts or replaces roster of participants into SQLite database."""
    if not records or not competition_id:
        return 0

    conn = db.get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    # Get competition prefix for cert ID
    cursor.execute("SELECT title FROM certificates_competitions WHERE id = ?", (competition_id,))
    comp_row = cursor.fetchone()
    title_slug = "CERT"
    if comp_row and comp_row["title"]:
        title_slug = re.sub(r'[^A-Za-z0-9]', '', comp_row["title"][:8]).upper()

    if replace_existing:
        cursor.execute("DELETE FROM certificate_participants WHERE competition_id = ?", (competition_id,))

    inserted = 0
    for idx, r in enumerate(records, start=1):
        name = r.get("name", "").strip()
        email = r.get("email", "").strip()
        rank = r.get("role_or_rank", "Participant").strip()

        if not name and not email:
            continue

        p_id = str(uuid.uuid4())
        # Generate clean cert serial: DEV-2026-SLUG-XXXXX
        cert_no = f"DEV-2026-{title_slug}-{uuid.uuid4().hex[:6].upper()}"

        cursor.execute("""
            INSERT INTO certificate_participants (
                id, competition_id, name, email, role_or_rank, certificate_number, issued_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (p_id, competition_id, name, email, rank, cert_no, datetime.now().strftime("%Y-%m-%d"), now))
        inserted += 1

    conn.commit()
    conn.close()
    return inserted
