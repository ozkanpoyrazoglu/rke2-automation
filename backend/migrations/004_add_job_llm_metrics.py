"""
Migration 004: Add LLM metrics to Job table

Adds fields to track LLM usage for job analysis:
- llm_model: the model ID used for analysis (e.g. "deepseek-r1")
- llm_token_count: total token count consumed for analysis

Usage:
    python migrations/004_add_job_llm_metrics.py upgrade
    python migrations/004_add_job_llm_metrics.py downgrade
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import SessionLocal

def upgrade():
    """Add LLM metrics fields to jobs table"""
    db = SessionLocal()
    try:
        print("Adding LLM metrics fields to jobs table...")

        # Add llm_model column (nullable, for tracking which model was used)
        db.execute(text("""
            ALTER TABLE jobs
            ADD COLUMN llm_model VARCHAR
        """))

        # Add llm_token_count column (nullable, for tracking token consumption)
        db.execute(text("""
            ALTER TABLE jobs
            ADD COLUMN llm_token_count INTEGER
        """))

        db.commit()
        print("✓ LLM metrics fields added successfully")

    except Exception as e:
        db.rollback()
        print(f"✗ Migration failed: {str(e)}")
        raise
    finally:
        db.close()

def downgrade():
    """Remove LLM metrics fields from jobs table"""
    db = SessionLocal()
    try:
        print("Removing LLM metrics fields from jobs table...")

        db.execute(text("ALTER TABLE jobs DROP COLUMN llm_model"))
        db.execute(text("ALTER TABLE jobs DROP COLUMN llm_token_count"))

        db.commit()
        print("✓ LLM metrics fields removed successfully")

    except Exception as e:
        db.rollback()
        print(f"✗ Downgrade failed: {str(e)}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 004_add_job_llm_metrics.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "upgrade":
        upgrade()
    elif command == "downgrade":
        downgrade()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python 004_add_job_llm_metrics.py [upgrade|downgrade]")
        sys.exit(1)
