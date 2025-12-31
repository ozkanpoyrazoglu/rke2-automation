"""
Migration 003: Add cluster operation lock fields

Adds fields to support cluster-level operation locking:
- operation_status: tracks if cluster is idle or running an operation
- current_job_id: references the currently running job
- operation_started_at: timestamp of when operation started
- operation_locked_by: type of operation (install/scale_add/scale_remove/uninstall)

Usage:
    python migrations/003_add_cluster_lock_fields.py upgrade
    python migrations/003_add_cluster_lock_fields.py downgrade
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal

def upgrade():
    """Add cluster lock fields"""
    db = SessionLocal()
    try:
        print("Adding cluster lock fields...")

        # Add operation_status column (default: idle)
        db.execute(text("""
            ALTER TABLE clusters
            ADD COLUMN operation_status VARCHAR DEFAULT 'idle'
        """))

        # Add current_job_id column
        db.execute(text("""
            ALTER TABLE clusters
            ADD COLUMN current_job_id INTEGER
        """))

        # Add operation_started_at column
        db.execute(text("""
            ALTER TABLE clusters
            ADD COLUMN operation_started_at TIMESTAMP
        """))

        # Add operation_locked_by column
        db.execute(text("""
            ALTER TABLE clusters
            ADD COLUMN operation_locked_by VARCHAR
        """))

        db.commit()
        print("✓ Cluster lock fields added successfully")

    except Exception as e:
        db.rollback()
        print(f"✗ Migration failed: {str(e)}")
        raise
    finally:
        db.close()

def downgrade():
    """Remove cluster lock fields"""
    db = SessionLocal()
    try:
        print("Removing cluster lock fields...")

        db.execute(text("ALTER TABLE clusters DROP COLUMN operation_status"))
        db.execute(text("ALTER TABLE clusters DROP COLUMN current_job_id"))
        db.execute(text("ALTER TABLE clusters DROP COLUMN operation_started_at"))
        db.execute(text("ALTER TABLE clusters DROP COLUMN operation_locked_by"))

        db.commit()
        print("✓ Cluster lock fields removed successfully")

    except Exception as e:
        db.rollback()
        print(f"✗ Downgrade failed: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 003_add_cluster_lock_fields.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "upgrade":
        upgrade()
    elif command == "downgrade":
        downgrade()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python 003_add_cluster_lock_fields.py [upgrade|downgrade]")
        sys.exit(1)
