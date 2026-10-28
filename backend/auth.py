"""
Authentication and session management for Devengers Platform.
Uses PBKDF2-HMAC-SHA256 and cryptographically secure tokens.
"""

import hashlib
import os
import secrets
from datetime import datetime, timezone, timedelta
from db import get_connection

ITERATIONS = 100_000
SESSION_DURATION_DAYS = 7
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    """Hashes a password with PBKDF2-HMAC-SHA256 and a random salt."""
    if salt is None:
        salt = secrets.token_bytes(32)
    pwd_bytes = password.encode('utf-8')
    derived = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt, ITERATIONS)
    return derived.hex(), salt.hex()

def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    """Verifies a plain password against the stored hash and salt."""
    salt = bytes.fromhex(salt_hex)
    pwd_bytes = password.encode('utf-8')
    derived = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt, ITERATIONS)
    return secrets.compare_digest(derived.hex(), password_hash)

def is_rate_limited(identifier: str) -> bool:
    """Checks whether the IP or email exceeded maximum login failures in lockout window."""
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
    cursor.execute("""
        SELECT COUNT(*) AS count FROM login_attempts
        WHERE ip_or_email = ? AND attempted_at >= ?
    """, (identifier, cutoff))
    row = cursor.fetchone()
    count = row["count"] if row else 0
    conn.close()
    return count >= MAX_FAILED_ATTEMPTS

def record_failed_attempt(identifier: str):
    """Records a failed login attempt for rate limiting."""
    conn = get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("INSERT INTO login_attempts (ip_or_email, attempted_at) VALUES (?, ?)", (identifier, now_iso))
    # Cleanup attempts older than 1 day
    cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    cursor.execute("DELETE FROM login_attempts WHERE attempted_at < ?", (cutoff,))
    conn.commit()
    conn.close()

def clear_failed_attempts(identifier: str):
    """Clears failed login attempts upon successful login."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM login_attempts WHERE ip_or_email = ?", (identifier,))
    conn.commit()
    conn.close()

def create_or_update_user(email: str, password: str, role: str = 'user', name: str = None) -> dict:
    """Creates a user or updates their password and role."""
    email = email.strip().lower()
    pwd_hash, salt_hex = hash_password(password)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    existing = cursor.fetchone()

    if existing:
        user_id = existing["id"]
        cursor.execute("""
            UPDATE users SET password_hash = ?, salt = ?, role = ?, name = COALESCE(?, name)
            WHERE id = ?
        """, (pwd_hash, salt_hex, role, name, user_id))
    else:
        import uuid
        user_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO users (id, email, password_hash, salt, role, name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, email, pwd_hash, salt_hex, role, name or email.split('@')[0], now_iso))

    conn.commit()
    conn.close()
    return {"id": user_id, "email": email, "role": role}

def reset_user_password(email: str, new_password: str) -> bool:
    """Updates password for an existing user and clears failed login attempts."""
    clean_email = email.strip().lower()
    pwd_hash, salt_hex = hash_password(new_password)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (clean_email,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return False
    user_id = user["id"]
    cursor.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (pwd_hash, salt_hex, user_id))
    # Invalidate all existing sessions for this user for security
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    clear_failed_attempts(clean_email)
    return True

import email_service

def init_otp_table():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_otps (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL COLLATE NOCASE,
            otp TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_used INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_email_otp ON email_otps(email, purpose, is_used);")
    conn.commit()
    conn.close()

def normalize_purpose(p: str) -> str:
    lp = str(p or '').lower()
    if 'reset' in lp or 'forgot' in lp or 'password' in lp:
        return "Password Reset"
    if 'sign' in lp:
        return "Sign Up Verification"
    if 'admin' in lp:
        return "Admin Login 2FA"
    return str(p or "Sign Up Verification")

def generate_and_store_otp(email: str, purpose: str = "Sign Up Verification") -> dict:
    """Generates a 6-digit cryptographic OTP, saves to DB, and dispatches via email service."""
    init_otp_table()
    clean_email = email.strip().lower()
    norm_purpose = normalize_purpose(purpose)
    otp_code = f"{secrets.randbelow(900000) + 100000}"
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=10)

    conn = get_connection()
    cursor = conn.cursor()

    # Invalidate previous unverified OTPs for this email and purpose
    cursor.execute("""
        UPDATE email_otps SET is_used = 1 
        WHERE email = ? AND purpose = ? AND is_used = 0
    """, (clean_email, norm_purpose))

    import uuid
    otp_id = str(uuid.uuid4())
    cursor.execute("""
        INSERT INTO email_otps (id, email, otp, purpose, expires_at, created_at, is_used)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (otp_id, clean_email, otp_code, norm_purpose, expires.isoformat(), now.isoformat()))

    # Clean up old records older than 1 day
    cutoff = (now - timedelta(days=1)).isoformat()
    cursor.execute("DELETE FROM email_otps WHERE created_at < ?", (cutoff,))

    conn.commit()
    conn.close()

    # Send email
    result = email_service.send_otp_email(clean_email, otp_code, purpose=norm_purpose)
    return result

def verify_otp(email: str, otp: str, purpose: str = "Sign Up Verification") -> bool:
    """Verifies that the provided OTP matches and has not expired."""
    init_otp_table()
    clean_email = email.strip().lower()
    clean_otp = str(otp).strip()
    norm_purpose = normalize_purpose(purpose)
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM email_otps 
        WHERE email = ? AND otp = ? AND purpose = ? AND is_used = 0 AND expires_at >= ?
        ORDER BY created_at DESC LIMIT 1
    """, (clean_email, clean_otp, norm_purpose, now_iso))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return False

    otp_id = row["id"]
    cursor.execute("UPDATE email_otps SET is_used = 1 WHERE id = ?", (otp_id,))
    conn.commit()
    conn.close()
    return True

def authenticate(email_or_user: str, password: str, client_ip: str = "127.0.0.1", otp: str = None) -> tuple[dict | None, str | None]:
    """Authenticates credentials. Admin users strictly require a 2FA OTP."""
    ident = email_or_user.strip().lower()
    if is_rate_limited(ident) or is_rate_limited(client_ip):
        return None, "Too many failed attempts. Please wait 15 minutes before trying again."

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (ident,))
    user = cursor.fetchone()

    if not user:
        record_failed_attempt(ident)
        record_failed_attempt(client_ip)
        conn.close()
        return None, "Invalid email or password."

    if not verify_password(password, user["password_hash"], user["salt"]):
        record_failed_attempt(ident)
        record_failed_attempt(client_ip)
        conn.close()
        return None, "Invalid email or password."

    # If user is admin (event@devengers.org or role == 'admin'), require 2FA OTP
    is_admin = (user["role"] == 'admin' or user["email"] == 'event@devengers.org')
    if is_admin:
        admin_email = "event@devengers.org"
        if not otp:
            # Generate and dispatch admin OTP automatically strictly to event@devengers.org
            admin_otp_result = generate_and_store_otp(admin_email, purpose="Admin Login 2FA")
            conn.close()
            dev_otp = admin_otp_result.get("dev_otp")
            return None, f"REQUIRES_ADMIN_OTP:{dev_otp or ''}"

        # Verify admin OTP strictly against event@devengers.org
        if not verify_otp(admin_email, otp, purpose="Admin Login 2FA"):
            record_failed_attempt(ident)
            conn.close()
            return None, "Invalid or expired Admin 2FA passcode sent to event@devengers.org."

    # Successful login
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_iso, user["id"]))
    conn.commit()
    conn.close()

    clear_failed_attempts(ident)
    clear_failed_attempts(client_ip)

    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"]
    }, None

def create_session(user_id: str, role: str, ip_address: str = None) -> str:
    """Creates a new session token stored in SQLite."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=SESSION_DURATION_DAYS)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (token, user_id, role, expires_at, created_at, ip_address)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (token, user_id, role, expires.isoformat(), now.isoformat(), ip_address))
    conn.commit()
    conn.close()
    return token

def get_session_user(token: str) -> dict | None:
    """Validates session token and returns associated user profile, role, rank, and progress."""
    if not token:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        SELECT s.token, s.expires_at, u.*
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ? AND s.expires_at > ?
    """, (token, now_iso))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    from db import get_user_completed_course_ids, get_user_applied_event_ids, calculate_user_streak
    user_id = row["id"]
    completed_ids = get_user_completed_course_ids(user_id)
    applied_ids = get_user_applied_event_ids(user_id)
    calculated_streak = calculate_user_streak(user_id)

    keys = row.keys()
    banner = row["banner_style"] if ("banner_style" in keys and row["banner_style"]) else (row["banner_color"] if ("banner_color" in keys and row["banner_color"]) else "gradient-purple")

    return {
        "id": user_id,
        "email": row["email"],
        "name": row["name"],
        "full_name": row["name"],
        "role": row["role"],
        "avatar_emoji": row["avatar_emoji"] if ("avatar_emoji" in keys and row["avatar_emoji"]) else "⚡",
        "avatar_url": row["avatar_url"] if ("avatar_url" in keys and row["avatar_url"]) else "",
        "banner_style": banner,
        "banner_color": banner,
        "bio": row["bio"] if ("bio" in keys and row["bio"]) else "",
        "target_role": row["target_role"] if ("target_role" in keys and row["target_role"]) else "B.Tech CSE / Full Stack",
        "streak_count": calculated_streak,
        "daily_streak": calculated_streak,
        "college_name": row["college_name"] if ("college_name" in keys and row["college_name"]) else "",
        "grad_year": row["grad_year"] if ("grad_year" in keys and row["grad_year"]) else "",
        "github_handle": row["github_handle"] if ("github_handle" in keys and row["github_handle"]) else "",
        "leetcode_handle": row["leetcode_handle"] if ("leetcode_handle" in keys and row["leetcode_handle"]) else "",
        "linkedin_url": row["linkedin_url"] if ("linkedin_url" in keys and row["linkedin_url"]) else "",
        "portfolio_url": row["portfolio_url"] if ("portfolio_url" in keys and row["portfolio_url"]) else "",
        "twitter_handle": row["twitter_handle"] if ("twitter_handle" in keys and row["twitter_handle"]) else "",
        "skills": row["skills"] if ("skills" in keys and row["skills"]) else "Python, JavaScript, React, DSA, SQL, Git",
        "questions_solved_total": row["questions_solved_total"] if ("questions_solved_total" in keys and row["questions_solved_total"]) else 0,
        "created_at": row["created_at"] if ("created_at" in keys and row["created_at"]) else "",
        "completed_course_ids": completed_ids,
        "applied_event_ids": applied_ids
    }


def delete_session(token: str):
    """Logs out by invalidating the session token."""
    if not token:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()

def authenticate_or_create_google_user(email: str, name: str = None, picture: str = None, google_id: str = None) -> tuple[dict | None, str | None]:
    """Authenticates or creates a user account via Google Sign-In."""
    clean_email = (email or '').strip().lower()
    if not clean_email or '@' not in clean_email:
        return None, "A valid email address is required from Google."

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (clean_email,))
    existing = cursor.fetchone()
    now_iso = datetime.now(timezone.utc).isoformat()

    if existing:
        user_id = existing["id"]
        role = existing["role"]
        # Update name and avatar if not yet set
        updates = []
        params = []
        if (not existing["name"] or existing["name"] == clean_email.split('@')[0]) and name:
            updates.append("name = ?")
            params.append(name)
        if ("avatar_url" in existing.keys() and not existing["avatar_url"]) and picture:
            updates.append("avatar_url = ?")
            params.append(picture)
        if updates:
            params.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
    else:
        import uuid
        user_id = str(uuid.uuid4())
        role = "admin" if clean_email == "event@devengers.org" else "student"
        pwd_hash, salt_hex = hash_password(secrets.token_urlsafe(32))
        user_name = name or clean_email.split('@')[0].capitalize()
        cursor.execute("""
            INSERT INTO users (id, email, password_hash, salt, role, name, avatar_url, created_at, target_role, skills)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'B.Tech CSE / Full Stack', 'Python, JavaScript, React, DSA, SQL, Git')
        """, (user_id, clean_email, pwd_hash, salt_hex, role, user_name, picture or "", now_iso))
        conn.commit()

    conn.close()

    # For admin account (event@devengers.org), 2FA OTP is required for security
    if role == 'admin' and clean_email == 'event@devengers.org':
        res = generate_and_store_otp(clean_email, purpose="Admin Login 2FA")
        return {
            "requires_otp": True,
            "email": clean_email,
            "dev_otp": res.get("dev_otp", ""),
            "message": "Admin Security Check: 6-digit 2FA passcode sent to event@devengers.org"
        }, None

    user = {
        "id": user_id,
        "email": clean_email,
        "name": name or clean_email.split('@')[0],
        "role": role,
        "avatar_url": picture or ""
    }
    return user, None

