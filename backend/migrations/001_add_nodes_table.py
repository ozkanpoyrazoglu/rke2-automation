"""
Migration: Add nodes table and migrate cluster.nodes JSON to Node records

This migration:
1. Creates the nodes table with proper schema
2. Migrates existing cluster.nodes JSON data to Node records
3. Removes the old nodes JSON column from clusters table

Usage:
    python migrations/001_add_nodes_table.py upgrade
    python migrations/001_add_nodes_table.py downgrade
"""

import sys
import json
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, JSON, ForeignKey, Enum, Boolean, UniqueConstraint, text
from sqlalchemy.orm import sessionmaker, declarative_base
import enum

# Database URL - read from environment or use SQLite default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/rke2.db")

Base = declarative_base()
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(bind=engine)


# Enums
class NodeRole(str, enum.Enum):
    INITIAL_MASTER = "initial_master"
    MASTER = "master"
    WORKER = "worker"


class NodeStatus(str, enum.Enum):
    PENDING = "pending"
    INSTALLING = "installing"
    ACTIVE = "active"
    FAILED = "failed"
    DRAINING = "draining"
    REMOVED = "removed"


# Simplified table definitions for migration (avoid ORM complexity)
def get_nodes_table():
    """Create nodes table using SQLAlchemy Core"""
    from sqlalchemy import Table, MetaData

    metadata = MetaData()

    nodes_table = Table(
        'nodes',
        metadata,
        Column('id', Integer, primary_key=True),
        Column('cluster_id', Integer, nullable=False),
        Column('hostname', String, nullable=False),
        Column('internal_ip', String, nullable=False),
        Column('external_ip', String, nullable=True),
        Column('role', String, nullable=False),
        Column('status', String, default='pending'),
        Column('use_external_ip', Boolean, default=False),
        Column('node_vars', JSON, nullable=True),
        Column('installation_started_at', DateTime, nullable=True),
        Column('installation_completed_at', DateTime, nullable=True),
        Column('installation_error', Text, nullable=True),
        Column('created_at', DateTime, default=datetime.utcnow),
        Column('updated_at', DateTime, default=datetime.utcnow),
        UniqueConstraint('cluster_id', 'hostname', name='uq_cluster_hostname'),
    )

    return metadata, nodes_table


def upgrade():
    """Apply migration"""
    print("=== Starting migration: Add nodes table ===")

    # Create nodes table
    print("Creating nodes table...")
    metadata, nodes_table = get_nodes_table()
    metadata.create_all(engine, checkfirst=True)
    print("✓ Nodes table created")

    # Migrate data
    print("\nMigrating cluster.nodes JSON to Node records...")
    db = SessionLocal()

    try:
        # Get all clusters with nodes data
        result = db.execute(text("SELECT id, name, nodes FROM clusters WHERE nodes IS NOT NULL"))
        clusters = result.fetchall()

        total_nodes_migrated = 0

        for cluster in clusters:
            cluster_id, cluster_name, nodes_json = cluster

            if not nodes_json:
                continue

            # Parse JSON
            try:
                nodes_data = json.loads(nodes_json) if isinstance(nodes_json, str) else nodes_json
            except (json.JSONDecodeError, TypeError):
                print(f"⚠ Warning: Could not parse nodes JSON for cluster {cluster_name}, skipping")
                continue

            if not isinstance(nodes_data, list):
                print(f"⚠ Warning: nodes data for cluster {cluster_name} is not a list, skipping")
                continue

            # Track if we've seen the first server
            first_server = True
            migrated_count = 0

            for node_data in nodes_data:
                # Determine role
                if node_data.get('role') == 'server':
                    role = NodeRole.INITIAL_MASTER if first_server else NodeRole.MASTER
                    first_server = False
                else:
                    role = NodeRole.WORKER

                # Extract IPs
                internal_ip = node_data.get('internal_ip') or node_data.get('ip')
                external_ip = node_data.get('external_ip')

                if not internal_ip:
                    print(f"⚠ Warning: Node {node_data.get('hostname')} has no IP, skipping")
                    continue

                # Insert node record directly
                db.execute(
                    text("""
                        INSERT INTO nodes (cluster_id, hostname, internal_ip, external_ip, role, status, use_external_ip, created_at, updated_at)
                        VALUES (:cluster_id, :hostname, :internal_ip, :external_ip, :role, :status, :use_external_ip, :created_at, :updated_at)
                    """),
                    {
                        "cluster_id": cluster_id,
                        "hostname": node_data.get('hostname'),
                        "internal_ip": internal_ip,
                        "external_ip": external_ip,
                        "role": role.value,
                        "status": NodeStatus.ACTIVE.value,
                        "use_external_ip": node_data.get('use_external_ip', False),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                )
                migrated_count += 1

            db.commit()
            total_nodes_migrated += migrated_count
            print(f"✓ Migrated {migrated_count} nodes for cluster '{cluster_name}'")

        print(f"\n✓ Total nodes migrated: {total_nodes_migrated}")

        # Add installation_stage column to clusters
        print("\nAdding installation_stage column to clusters table...")
        try:
            db.execute(text("ALTER TABLE clusters ADD COLUMN installation_stage VARCHAR"))
            # Mark clusters with nodes as completed
            db.execute(text("UPDATE clusters SET installation_stage = 'completed' WHERE id IN (SELECT DISTINCT cluster_id FROM nodes)"))
            db.commit()
            print("✓ installation_stage column added")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("✓ installation_stage column already exists")
                db.rollback()
            else:
                raise

        # Add cluster_vars column to clusters
        print("\nAdding cluster_vars column to clusters table...")
        try:
            db.execute(text("ALTER TABLE clusters ADD COLUMN cluster_vars JSON"))
            db.commit()
            print("✓ cluster_vars column added")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("✓ cluster_vars column already exists")
                db.rollback()
            else:
                raise

        # Drop old nodes column from clusters
        print("\nDropping old nodes JSON column from clusters table...")
        try:
            db.execute(text("ALTER TABLE clusters DROP COLUMN nodes"))
            db.commit()
            print("✓ Old nodes column dropped")
        except Exception as e:
            if "does not exist" in str(e).lower() or "no such column" in str(e).lower():
                print("✓ Old nodes column already removed")
                db.rollback()
            else:
                print(f"⚠ Warning: Could not drop nodes column: {e}")
                db.rollback()

        print("\n=== Migration completed successfully ===")

    except Exception as e:
        db.rollback()
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        db.close()


def downgrade():
    """Revert migration"""
    print("=== Starting rollback: Remove nodes table ===")

    db = SessionLocal()

    try:
        # Add back nodes column
        print("Adding back nodes JSON column to clusters table...")
        try:
            db.execute(text("ALTER TABLE clusters ADD COLUMN nodes JSON"))
            db.commit()
            print("✓ Nodes column added back")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("✓ Nodes column already exists")
                db.rollback()
            else:
                raise

        # Migrate Node records back to JSON (database-agnostic approach)
        print("\nMigrating Node records back to clusters.nodes JSON...")

        # Get all clusters
        from sqlalchemy import select
        cluster_results = db.execute(text("SELECT id, name FROM clusters"))
        all_clusters = cluster_results.fetchall()

        for cluster_id, cluster_name in all_clusters:
            # Get nodes for this cluster
            node_results = db.execute(
                text("SELECT hostname, internal_ip, external_ip, role, use_external_ip FROM nodes WHERE cluster_id = :cid AND status != 'removed'"),
                {"cid": cluster_id}
            )
            nodes = node_results.fetchall()

            if nodes:
                nodes_list = []
                for hostname, internal_ip, external_ip, role, use_external_ip in nodes:
                    # Convert role back to old format
                    old_role = "server" if role in ["initial_master", "master"] else "agent"
                    nodes_list.append({
                        "hostname": hostname,
                        "ip": internal_ip,
                        "internal_ip": internal_ip,
                        "external_ip": external_ip,
                        "role": old_role,
                        "use_external_ip": bool(use_external_ip)
                    })

                # Update cluster with nodes JSON
                db.execute(
                    text("UPDATE clusters SET nodes = :nodes WHERE id = :id"),
                    {"nodes": json.dumps(nodes_list), "id": cluster_id}
                )
                print(f"✓ Migrated {len(nodes_list)} nodes back for cluster '{cluster_name}'")

        db.commit()

        # Drop nodes table
        print("\nDropping nodes table...")
        metadata, nodes_table = get_nodes_table()
        metadata.drop_all(engine, checkfirst=True)
        print("✓ Nodes table dropped")

        # Drop added columns
        print("\nDropping installation_stage column...")
        try:
            db.execute(text("ALTER TABLE clusters DROP COLUMN installation_stage"))
            db.commit()
            print("✓ installation_stage column dropped")
        except Exception as e:
            print(f"⚠ Warning: {e}")
            db.rollback()

        print("\nDropping cluster_vars column...")
        try:
            db.execute(text("ALTER TABLE clusters DROP COLUMN cluster_vars"))
            db.commit()
            print("✓ cluster_vars column dropped")
        except Exception as e:
            print(f"⚠ Warning: {e}")
            db.rollback()

        print("\n=== Rollback completed successfully ===")

    except Exception as e:
        db.rollback()
        print(f"\n✗ Rollback failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python 001_add_nodes_table.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "upgrade":
        upgrade()
    elif command == "downgrade":
        downgrade()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python 001_add_nodes_table.py [upgrade|downgrade]")
        sys.exit(1)
