"""
Fix enum values in database - uppercase them to match Python enums
"""

import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/rke2.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(bind=engine)

def upgrade():
    """Fix enum values to uppercase"""
    print("=== Fixing enum values ===")

    db = SessionLocal()

    try:
        # Fix NodeRole values
        print("Updating NodeRole values to uppercase...")

        db.execute(text("UPDATE nodes SET role = 'INITIAL_MASTER' WHERE role = 'initial_master'"))
        db.execute(text("UPDATE nodes SET role = 'MASTER' WHERE role = 'master'"))
        db.execute(text("UPDATE nodes SET role = 'WORKER' WHERE role = 'worker'"))

        # Fix NodeStatus values
        print("Updating NodeStatus values to uppercase...")

        db.execute(text("UPDATE nodes SET status = 'PENDING' WHERE status = 'pending'"))
        db.execute(text("UPDATE nodes SET status = 'INSTALLING' WHERE status = 'installing'"))
        db.execute(text("UPDATE nodes SET status = 'ACTIVE' WHERE status = 'active'"))
        db.execute(text("UPDATE nodes SET status = 'FAILED' WHERE status = 'failed'"))
        db.execute(text("UPDATE nodes SET status = 'DRAINING' WHERE status = 'draining'"))
        db.execute(text("UPDATE nodes SET status = 'REMOVED' WHERE status = 'removed'"))

        db.commit()

        # Verify
        result = db.execute(text("SELECT DISTINCT role FROM nodes"))
        roles = [row[0] for row in result.fetchall()]
        print(f"✓ Roles updated: {roles}")

        result = db.execute(text("SELECT DISTINCT status FROM nodes"))
        statuses = [row[0] for row in result.fetchall()]
        print(f"✓ Statuses updated: {statuses}")

        print("\n=== Migration completed successfully ===")

    except Exception as e:
        db.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        db.close()

def downgrade():
    """Revert to lowercase"""
    print("=== Reverting enum values to lowercase ===")

    db = SessionLocal()

    try:
        db.execute(text("UPDATE nodes SET role = 'initial_master' WHERE role = 'INITIAL_MASTER'"))
        db.execute(text("UPDATE nodes SET role = 'master' WHERE role = 'MASTER'"))
        db.execute(text("UPDATE nodes SET role = 'worker' WHERE role = 'WORKER'"))

        db.execute(text("UPDATE nodes SET status = 'pending' WHERE status = 'PENDING'"))
        db.execute(text("UPDATE nodes SET status = 'installing' WHERE status = 'INSTALLING'"))
        db.execute(text("UPDATE nodes SET status = 'active' WHERE status = 'ACTIVE'"))
        db.execute(text("UPDATE nodes SET status = 'failed' WHERE status = 'FAILED'"))
        db.execute(text("UPDATE nodes SET status = 'draining' WHERE status = 'DRAINING'"))
        db.execute(text("UPDATE nodes SET status = 'removed' WHERE status = 'REMOVED'"))

        db.commit()
        print("\n=== Rollback completed successfully ===")

    except Exception as e:
        db.rollback()
        print(f"\n✗ Rollback failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 002_fix_enum_values.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "upgrade":
        upgrade()
    elif command == "downgrade":
        downgrade()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
