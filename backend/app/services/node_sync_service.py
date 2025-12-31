"""
Node Sync Service

Synchronizes database node statuses with actual cluster state from inspection.
This ensures database reflects reality when nodes are installed/active.
"""

from sqlalchemy.orm import Session
from app.models import Cluster, Node, NodeStatus
from app.services.cluster_status_service import get_cluster_status
from typing import Dict, List
import re


def sync_node_statuses_from_inspection(db: Session, cluster_id: int) -> Dict:
    """
    Sync node statuses from cluster inspection to database.

    Updates Node.status based on actual Kubernetes node status.

    Returns:
        {
            "synced": int,  # Number of nodes updated
            "errors": []    # List of errors
        }
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        return {"synced": 0, "errors": ["Cluster not found"]}

    if cluster.cluster_type != "new":
        return {"synced": 0, "errors": ["Can only sync 'new' type clusters"]}

    # Get cluster inspection
    try:
        inspection = get_cluster_status(cluster)
    except Exception as e:
        return {"synced": 0, "errors": [f"Failed to get cluster status: {str(e)}"]}

    if not inspection or "nodes" not in inspection:
        return {"synced": 0, "errors": ["No node data in inspection"]}

    # Build mapping of IP -> Kubernetes node status
    k8s_nodes = {}
    for node_detail in inspection["nodes"].get("details", []):
        internal_ip = node_detail.get("internal_ip")
        k8s_status = node_detail.get("status", "Unknown")
        roles = node_detail.get("roles", "")

        if internal_ip:
            k8s_nodes[internal_ip] = {
                "status": k8s_status,
                "roles": roles,
                "name": node_detail.get("name")
            }

    # Update database nodes
    db_nodes = db.query(Node).filter(Node.cluster_id == cluster_id).all()
    synced_count = 0
    errors = []

    for db_node in db_nodes:
        k8s_node = k8s_nodes.get(db_node.internal_ip)

        if not k8s_node:
            # Node not found in Kubernetes - might be removed or not yet joined
            continue

        # Map Kubernetes status to our NodeStatus
        new_status = None
        if k8s_node["status"] == "Ready":
            new_status = NodeStatus.ACTIVE
        elif k8s_node["status"] in ["NotReady", "Unknown"]:
            new_status = NodeStatus.FAILED

        # Update if status changed
        if new_status and db_node.status != new_status:
            old_status = db_node.status
            db_node.status = new_status
            synced_count += 1
            print(f"Updated {db_node.hostname}: {old_status.value} -> {new_status.value}")

    if synced_count > 0:
        db.commit()

    return {
        "synced": synced_count,
        "errors": errors,
        "total_k8s_nodes": len(k8s_nodes),
        "total_db_nodes": len(db_nodes)
    }


def auto_sync_on_inspection(db: Session, cluster_id: int):
    """
    Automatically sync node statuses when inspection is performed.
    Called from cluster status/refresh endpoints.
    """
    try:
        result = sync_node_statuses_from_inspection(db, cluster_id)
        if result["synced"] > 0:
            print(f"Auto-synced {result['synced']} node(s) for cluster {cluster_id}")
    except Exception as e:
        print(f"Auto-sync failed for cluster {cluster_id}: {str(e)}")
