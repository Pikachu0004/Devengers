"""
Devengers Turso Database Migration & Sync Utility.
Migrates all local SQLite schemas and data (Users, Events, Courses, Certificates, Gallery)
directly to your Turso Cloud SQLite database in one single execution.
"""

import os
import sys
import sqlite3

# Ensure backend directory is in path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from db import DB_PATH, init_db
from turso_client import is_turso_configured, get_turso_connection

def sync_to_turso():
    print("=" * 64)
    print("      DEVENGERS -> TURSO CLOUD DATABASE MIGRATION TOOL")
    print("=" * 64)

    if not is_turso_configured():
        print("❌ Error: Turso is not configured in your environment.")
        print("Please set the following environment variables before running:")
        print("  export TURSO_DATABASE_URL='https://devengers-yourorg.turso.io'")
        print("  export TURSO_AUTH_TOKEN='your_turso_auth_token'")
        print("=" * 64)
        return False

    turso_conn = get_turso_connection()
    if not turso_conn:
        print("❌ Error: Failed to initialize Turso connection.")
        return False

    print(f"✓ Turso Cloud Database: {turso_conn.base_url}")
    print(f"✓ Local Source Database: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print(f"❌ Error: Source local database not found at {DB_PATH}")
        return False

    local_conn = sqlite3.connect(DB_PATH)
    local_conn.row_factory = sqlite3.Row
    local_cur = local_conn.cursor()

    # Get all tables
    local_cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = local_cur.fetchall()
    print(f"\nDiscovered {len(tables)} tables to migrate:")
    for t in tables:
        print(f"  - {t['name']}")

    turso_cur = turso_conn.cursor()

    total_rows_synced = 0

    for t in tables:
        tbl_name = t['name']
        create_sql = t['sql']

        print(f"\n[Migrating Table: {tbl_name}]")
        # Create table in Turso
        try:
            turso_cur.execute(create_sql)
            print(f"  ✓ Schema validated / created on Turso")
        except Exception as e:
            print(f"  ⚠️ Schema note: {e}")

        # Fetch local data
        local_cur.execute(f"SELECT * FROM {tbl_name}")
        rows = local_cur.fetchall()
        if not rows:
            print(f"  (0 rows to transfer)")
            continue

        col_names = [d[0] for d in local_cur.description]
        placeholders = ", ".join(["?"] * len(col_names))
        cols_str = ", ".join([f'"{c}"' for c in col_names])
        insert_sql = f'INSERT OR REPLACE INTO "{tbl_name}" ({cols_str}) VALUES ({placeholders})'

        synced_in_table = 0
        for r in rows:
            values = tuple(r[c] for c in col_names)
            try:
                turso_cur.execute(insert_sql, values)
                synced_in_table += 1
            except Exception as e:
                print(f"  ❌ Error inserting into {tbl_name}: {e}")

        total_rows_synced += synced_in_table
        print(f"  ✓ Successfully migrated {synced_in_table} rows")

    local_conn.close()

    print("\n" + "=" * 64)
    print(f"🎉 MIGRATION COMPLETE! Total rows copied to Turso: {total_rows_synced}")
    print("Your Devengers Platform on Render is now backed by a persistent cloud SQLite database!")
    print("=" * 64)
    return True

if __name__ == "__main__":
    sync_to_turso()

