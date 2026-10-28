#!/usr/bin/env python3
"""
CLI tool for secure administrator provisioning and password management.
Run this command on the server or locally to manage the DEVENGERS admin account.

Usage:
  python3 manage_admin.py set-password event@devengers.org [optional_password]
  python3 manage_admin.py list
  python3 manage_admin.py init
"""

import sys
import os
import getpass
import secrets
from db import init_db, get_connection
from auth import create_or_update_user

ADMIN_EMAIL = "event@devengers.org"

def main():
    init_db()

    if len(sys.argv) < 2:
        print("Devengers Admin Management CLI")
        print("Commands:")
        print("  set-password <email> [password]  - Set or reset user/admin password")
        print("  init                             - Ensure default admin is provisioned")
        print("  list                             - List accounts and roles")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "set-password":
        email = sys.argv[2] if len(sys.argv) > 2 else ADMIN_EMAIL
        role = "admin" if email.lower() == ADMIN_EMAIL.lower() else "user"
        if len(sys.argv) > 3:
            password = sys.argv[3]
        else:
            password = getpass.getpass(f"Enter new password for {email}: ")
            confirm = getpass.getpass("Confirm password: ")
            if password != confirm:
                print("Error: Passwords do not match.")
                sys.exit(1)

        if len(password) < 6:
            print("Error: Password must be at least 6 characters.")
            sys.exit(1)

        user = create_or_update_user(email, password, role=role)
        print(f"Successfully updated {user['email']} with role: {user['role']}")

    elif cmd == "init":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, role FROM users WHERE email = ?", (ADMIN_EMAIL,))
        existing = cursor.fetchone()
        conn.close()

        if existing:
            print(f"Administrator {ADMIN_EMAIL} is already provisioned.")
        else:
            # Check environment variable first
            env_pwd = os.environ.get("DEVENGERS_ADMIN_PASSWORD")
            if env_pwd:
                pwd = env_pwd
                print(f"Provisioned administrator {ADMIN_EMAIL} from DEVENGERS_ADMIN_PASSWORD.")
            else:
                # Generate a temporary random password
                pwd = secrets.token_urlsafe(12)
                print("="*60)
                print(f"INITIAL ADMINISTRATOR ACCOUNT PROVISIONED:")
                print(f"Email:    {ADMIN_EMAIL}")
                print(f"Password: {pwd}")
                print("Please change this password via: python3 manage_admin.py set-password")
                print("="*60)

            create_or_update_user(ADMIN_EMAIL, pwd, role="admin", name="Devengers Event Admin")

    elif cmd == "list":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, role, name, created_at, last_login FROM users ORDER BY created_at")
        rows = cursor.fetchall()
        conn.close()
        print(f"{'EMAIL':<30} {'ROLE':<10} {'NAME':<20} {'LAST LOGIN'}")
        print("-" * 75)
        for r in rows:
            print(f"{r['email']:<30} {r['role']:<10} {r['name'] or '':<20} {r['last_login'] or 'Never'}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()
