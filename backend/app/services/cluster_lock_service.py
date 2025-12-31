"""
Cluster Lock Service

Provides cluster-level operation locking to prevent concurrent operations
and implements safety guardrails before executing operations.
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime
from app.models import Cluster, Node, NodeRole, NodeStatus, Job
from typing import Optional, List, Dict, Tuple
import socket


class ClusterLockError(Exception):
    """Raised when cluster lock cannot be acquired"""
    pass


class GuardrailError(Exception):
    """Raised when a guardrail check fails"""
    pass


def acquire_cluster_lock(
    db: Session,
    cluster_id: int,
    job_id: int,
    operation_type: str
) -> Cluster:
    """
    Acquire exclusive lock on cluster for an operation.

    Args:
        db: Database session
        cluster_id: Cluster to lock
        job_id: Job ID that will run
        operation_type: Type of operation (install/scale_add/scale_remove/uninstall)

    Returns:
        Locked cluster object

    Raises:
        HTTPException(409) if cluster is already locked
    """
    # Use SELECT FOR UPDATE to prevent race conditions
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).with_for_update().first()

    if not cluster:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    # Check if already locked
    if cluster.operation_status == "running":
        raise HTTPException(
            status_code=409,
            detail=f"Cluster is busy with operation '{cluster.operation_locked_by}' (job {cluster.current_job_id}). Please wait for it to complete."
        )

    # Acquire lock
    cluster.operation_status = "running"
    cluster.current_job_id = job_id
    cluster.operation_started_at = datetime.utcnow()
    cluster.operation_locked_by = operation_type

    db.commit()
    db.refresh(cluster)

    return cluster


def release_cluster_lock(db: Session, cluster_id: int):
    """
    Release cluster lock after operation completes.

    Args:
        db: Database session
        cluster_id: Cluster to unlock
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

    if cluster:
        cluster.operation_status = "idle"
        cluster.current_job_id = None
        cluster.operation_started_at = None
        cluster.operation_locked_by = None
        db.commit()


def check_bootstrap_prerequisite(db: Session, cluster_id: int) -> Tuple[bool, Optional[str]]:
    """
    G1: Check if initial_master is active before allowing joins.

    Returns:
        (is_valid, error_message)
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()

    # Find initial master
    initial_master = db.query(Node).filter(
        Node.cluster_id == cluster_id,
        Node.role == NodeRole.INITIAL_MASTER
    ).first()

    if not initial_master:
        return False, "No initial master found. Cannot add joining masters or workers until initial master is created."

    if initial_master.status != NodeStatus.ACTIVE:
        return False, f"Initial master '{initial_master.hostname}' is not active (status: {initial_master.status.value}). Cannot add nodes until initial master is fully operational."

    # Best-effort connectivity check (check if RKE2 API port is reachable)
    # This is optional - don't block on connectivity issues (could be firewall, network, etc.)
    if cluster.rke2_api_ip:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((cluster.rke2_api_ip, 9345))
            sock.close()

            if result != 0:
                # Just log warning, don't block the operation
                print(f"Warning: Initial master API endpoint {cluster.rke2_api_ip}:9345 is not reachable (this may be expected due to firewall)")
        except Exception as e:
            # Don't fail on connectivity check errors, just log
            print(f"Warning: Could not check API connectivity: {str(e)}")

    return True, None


def check_safe_master_removal(
    db: Session,
    cluster_id: int,
    nodes_to_remove: List[Dict],
    require_confirmation: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    G2: Prevent unsafe master removal (already implemented in routers/clusters.py).

    This validates:
    - Not removing last control-plane node
    - Not breaking etcd quorum
    - Confirmation flag for master removal

    Returns:
        (is_valid, error_message)
    """
    current_nodes = db.query(Node).filter(
        Node.cluster_id == cluster_id,
        Node.status != NodeStatus.REMOVED
    ).all()

    current_servers = [n for n in current_nodes if n.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]]
    removing_servers = [n for n in nodes_to_remove if n.get("role") == "server"]

    # Check if removing last control-plane
    if len(current_servers) - len(removing_servers) < 1:
        return False, "Cannot remove all control-plane nodes. At least 1 required."

    # Check etcd quorum (simple heuristic)
    remaining_servers = len(current_servers) - len(removing_servers)

    # If we'd have less than 3 servers remaining, warn
    if len(current_servers) > 1 and remaining_servers < 3:
        # For 2 remaining servers (even number), strongly discourage
        if remaining_servers == 2:
            return False, f"Removing {len(removing_servers)} server(s) would leave {remaining_servers} servers (even number). This is not recommended for etcd quorum. Consider removing one more or adding another master first."

    # Check majority quorum
    if len(current_servers) > 1 and remaining_servers < (len(current_servers) // 2 + 1):
        return False, f"Removing {len(removing_servers)} server(s) would break etcd quorum. Need at least {len(current_servers) // 2 + 1} servers."

    # Require confirmation for master removal
    if removing_servers and require_confirmation:
        return False, "Removing control-plane nodes requires explicit confirmation. Add 'confirm_master_removal=true' to your request."

    return True, None


def check_node_identity(
    db: Session,
    cluster_id: int,
    nodes_to_add: List[Dict]
) -> Tuple[bool, Optional[str]]:
    """
    G4: Validate node identity - prevent duplicates.

    Returns:
        (is_valid, error_message)
    """
    existing_nodes = db.query(Node).filter(
        Node.cluster_id == cluster_id,
        Node.status != NodeStatus.REMOVED
    ).all()

    existing_hostnames = {n.hostname for n in existing_nodes}
    existing_ips = {n.internal_ip for n in existing_nodes}

    for node in nodes_to_add:
        hostname = node.get('hostname')
        ip = node.get('ip')

        if hostname in existing_hostnames:
            return False, f"Node with hostname '{hostname}' already exists in cluster"

        if ip in existing_ips:
            return False, f"Node with IP '{ip}' already exists in cluster"

    return True, None


def split_master_worker_additions(
    nodes_to_add: List[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """
    G3: Split master and worker additions for sequential execution.

    Returns:
        (master_nodes, worker_nodes)
    """
    master_nodes = [n for n in nodes_to_add if n.get('role') == 'server']
    worker_nodes = [n for n in nodes_to_add if n.get('role') == 'agent']

    return master_nodes, worker_nodes


def update_installation_stage(db: Session, cluster_id: int):
    """
    Opportunistic installation stage tracking.
    Updates stage based on current node statuses.
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        return

    nodes = db.query(Node).filter(
        Node.cluster_id == cluster_id,
        Node.status != NodeStatus.REMOVED
    ).all()

    masters = [n for n in nodes if n.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]]
    workers = [n for n in nodes if n.role == NodeRole.WORKER]

    active_masters = [n for n in masters if n.status == NodeStatus.ACTIVE]
    active_workers = [n for n in workers if n.status == NodeStatus.ACTIVE]

    # Update stage opportunistically
    if not active_masters:
        # No active masters yet
        cluster.installation_stage = "pending"
    elif active_masters and not workers:
        # Only masters, no workers added yet
        cluster.installation_stage = "control_plane_ready"
    elif active_masters and workers and not active_workers:
        # Workers exist but not active yet
        cluster.installation_stage = "workers_installing"
    elif active_masters and active_workers:
        # Both masters and workers active
        if len(active_masters) == len(masters) and len(active_workers) == len(workers):
            # All nodes active
            cluster.installation_stage = "active"
        else:
            cluster.installation_stage = "workers_ready"

    db.commit()
