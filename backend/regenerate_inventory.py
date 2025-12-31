#!/usr/bin/env python3
"""
Utility script to regenerate Ansible inventory for existing clusters.
Useful if inventory files were manually deleted or corrupted.
"""

import sys
from app.database import SessionLocal
from app.models import Cluster
from app.services.ansible_generator import generate_ansible_artifacts
import os

def regenerate_cluster_inventory(cluster_id: int):
    """Regenerate inventory for a specific cluster"""
    db = SessionLocal()
    try:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            print(f"ERROR: Cluster {cluster_id} not found")
            return False

        if not cluster.cluster_nodes:
            print(f"ERROR: Cluster {cluster.name} has no nodes")
            return False

        print(f"Regenerating inventory for cluster: {cluster.name}")
        print(f"  - Nodes: {len(cluster.cluster_nodes)}")

        artifacts_dir = f"/ansible/clusters/{cluster.name}"
        os.makedirs(artifacts_dir, exist_ok=True)

        generate_ansible_artifacts(cluster, artifacts_dir)

        print(f"SUCCESS: Inventory regenerated at {artifacts_dir}")
        return True

    except Exception as e:
        print(f"ERROR: {str(e)}")
        return False
    finally:
        db.close()

def regenerate_all_inventories():
    """Regenerate inventory for all clusters"""
    db = SessionLocal()
    try:
        clusters = db.query(Cluster).all()
        print(f"Found {len(clusters)} clusters")

        success_count = 0
        for cluster in clusters:
            if cluster.cluster_nodes:
                print(f"\nRegenerating: {cluster.name}")
                artifacts_dir = f"/ansible/clusters/{cluster.name}"
                os.makedirs(artifacts_dir, exist_ok=True)

                try:
                    generate_ansible_artifacts(cluster, artifacts_dir)
                    print(f"  ✓ Success")
                    success_count += 1
                except Exception as e:
                    print(f"  ✗ Failed: {str(e)}")
            else:
                print(f"\nSkipping {cluster.name}: No nodes")

        print(f"\n{success_count}/{len(clusters)} clusters regenerated successfully")

    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--all":
            regenerate_all_inventories()
        else:
            cluster_id = int(sys.argv[1])
            regenerate_cluster_inventory(cluster_id)
    else:
        print("Usage:")
        print("  python regenerate_inventory.py <cluster_id>  # Regenerate specific cluster")
        print("  python regenerate_inventory.py --all         # Regenerate all clusters")
