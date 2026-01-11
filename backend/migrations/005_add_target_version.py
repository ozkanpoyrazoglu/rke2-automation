import sqlite3
import sys

def run_migration():
    """Add target_version column to jobs table"""
    import os
    # Try Docker path first, fall back to local path
    db_path = "/data/rke2.db" if os.path.exists("/data") else "data/rke2.db"

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'target_version' not in columns:
            print("Adding target_version column to jobs table...")
            cursor.execute("""
                ALTER TABLE jobs ADD COLUMN target_version TEXT NULL
            """)
            conn.commit()
            print("✅ Migration 005 completed: target_version column added")
        else:
            print("⚠️ target_version column already exists, skipping migration")

        conn.close()
        return True
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
