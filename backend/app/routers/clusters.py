from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Cluster, Job, ClusterType, JobStatus, Node, NodeRole, NodeStatus
from app.schemas import ClusterCreateNew, ClusterCreateRegistered, ClusterResponse
from app.services.cluster_service import create_new_cluster, register_cluster
from app.services.cluster_status_service import get_cluster_status
from app.services.kubeconfig_service import fetch_kubeconfig_from_master
from app.services.cluster_cache_service import get_cached_status, save_cache, invalidate_cache

router = APIRouter()

@router.post("/new", response_model=ClusterResponse)
async def create_cluster(
    cluster: ClusterCreateNew,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new RKE2 cluster (generates Ansible artifacts, does not execute)"""
    existing = db.query(Cluster).filter(Cluster.name == cluster.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cluster name already exists")

    new_cluster = create_new_cluster(db, cluster)
    return new_cluster

@router.post("/register", response_model=ClusterResponse)
async def register_existing_cluster(
    cluster: ClusterCreateRegistered,
    db: Session = Depends(get_db)
):
    """Register an existing cluster via kubeconfig"""
    existing = db.query(Cluster).filter(Cluster.name == cluster.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Cluster name already exists")

    registered = register_cluster(db, cluster)
    return registered

@router.get("", response_model=List[ClusterResponse])
async def list_clusters(db: Session = Depends(get_db)):
    """List all clusters"""
    clusters = db.query(Cluster).all()
    return clusters

@router.get("/{cluster_id}", response_model=ClusterResponse)
async def get_cluster(cluster_id: int, db: Session = Depends(get_db)):
    """Get cluster details"""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    return cluster

@router.get("/{cluster_id}/status")
async def get_cluster_status_endpoint(cluster_id: int, db: Session = Depends(get_db)):
    """
    Get cluster Kubernetes status via kubectl (cached with TTL)

    Returns cached data if available and valid.
    Otherwise collects fresh data and caches it.
    """
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Try to get cached data
    cached = get_cached_status(db, cluster_id, force_refresh=False)
    if cached:
        return cached

    # Cache miss or expired - collect fresh data
    status = get_cluster_status(cluster)

    # Save to cache if collection was successful
    if "error" not in status and "_collection_duration_seconds" in status:
        collection_duration = status.pop("_collection_duration_seconds")
        save_cache(db, cluster_id, status, collection_duration)

        # Auto-sync node statuses when we collect fresh data
        from app.services.node_sync_service import auto_sync_on_inspection
        auto_sync_on_inspection(db, cluster_id)

    return status

@router.post("/{cluster_id}/refresh")
async def refresh_cluster_status(cluster_id: int, db: Session = Depends(get_db)):
    """
    Force refresh cluster status (ignores cache TTL)

    Collects fresh data and updates cache.
    Also auto-syncs node statuses from Kubernetes to database.
    """
    from app.services.node_sync_service import auto_sync_on_inspection

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # Force collect fresh data (ignore cache)
    status = get_cluster_status(cluster)

    # Save to cache if collection was successful
    if "error" not in status and "_collection_duration_seconds" in status:
        collection_duration = status.pop("_collection_duration_seconds")
        save_cache(db, cluster_id, status, collection_duration)

    # Auto-sync node statuses from Kubernetes to database
    auto_sync_on_inspection(db, cluster_id)

    return status

@router.put("/{cluster_id}", response_model=ClusterResponse)
async def update_cluster(cluster_id: int, cluster_update: dict, db: Session = Depends(get_db)):
    """Update cluster metadata"""
    import subprocess

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    # If name is being changed and it's a 'new' cluster, rename the ansible directory
    old_name = cluster.name
    if "name" in cluster_update and cluster_update["name"] != old_name and cluster.cluster_type == ClusterType.NEW:
        new_name = cluster_update["name"]
        old_dir = f"/ansible/clusters/{old_name}"
        new_dir = f"/ansible/clusters/{new_name}"

        # Rename directory in ansible container if it exists
        try:
            subprocess.run([
                "docker", "exec", "rke2-automation-ansible-runner-1",
                "mv", old_dir, new_dir
            ], check=False)  # Don't fail if directory doesn't exist
        except:
            pass  # Ignore errors - directory might not exist yet

    # Update allowed fields
    allowed_fields = ["name", "rke2_version", "cni", "rke2_data_dir", "rke2_api_ip", "rke2_token", "rke2_additional_sans"]
    for field in allowed_fields:
        if field in cluster_update:
            setattr(cluster, field, cluster_update[field])

    db.commit()
    db.refresh(cluster)
    return cluster

@router.post("/{cluster_id}/fetch-kubeconfig")
async def fetch_kubeconfig(cluster_id: int, db: Session = Depends(get_db)):
    """Fetch kubeconfig from master node via SSH"""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if cluster.cluster_type != "new":
        raise HTTPException(status_code=400, detail="Can only fetch kubeconfig for 'new' type clusters")

    try:
        kubeconfig = fetch_kubeconfig_from_master(cluster)

        # Save to database
        cluster.kubeconfig = kubeconfig
        db.commit()
        db.refresh(cluster)

        return {"message": "Kubeconfig fetched successfully", "kubeconfig": kubeconfig}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch kubeconfig: {str(e)}")

@router.post("/{cluster_id}/upload-kubeconfig")
async def upload_kubeconfig(cluster_id: int, kubeconfig: dict, db: Session = Depends(get_db)):
    """Upload kubeconfig manually"""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    kubeconfig_content = kubeconfig.get("content")
    if not kubeconfig_content:
        raise HTTPException(status_code=400, detail="Kubeconfig content is required")

    cluster.kubeconfig = kubeconfig_content
    db.commit()
    db.refresh(cluster)

    return {"message": "Kubeconfig uploaded successfully"}

@router.delete("/{cluster_id}")
async def delete_cluster(cluster_id: int, db: Session = Depends(get_db)):
    """Delete a cluster"""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    db.delete(cluster)
    db.commit()
    return {"message": "Cluster deleted"}

# ==================== SCALE ENDPOINTS ====================

@router.get("/{cluster_id}/scale")
async def get_scale_info(cluster_id: int, db: Session = Depends(get_db)):
    """
    Get current cluster nodes for scaling operations

    Uses kubectl to get real-time node information from the cluster

    Returns:
        - Current nodes with roles from kubectl
        - Cluster metadata
    """
    from app.services.cluster_status_service import get_cluster_status

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if cluster.cluster_type != ClusterType.NEW:
        raise HTTPException(status_code=400, detail="Can only scale 'new' type clusters")

    if not cluster.kubeconfig:
        raise HTTPException(status_code=400, detail="Kubeconfig not available. Please fetch or upload kubeconfig first.")

    # Get real-time cluster status from kubectl
    try:
        status = get_cluster_status(cluster)
        node_details = status.get("nodes", {}).get("details", [])

        # Convert kubectl node data to scale-friendly format
        nodes = []
        for node in node_details:
            # Determine role from node roles
            role = "agent"
            node_roles = node.get("roles", "")
            if "control-plane" in node_roles or "master" in node_roles:
                role = "server"

            nodes.append({
                "hostname": node.get("name"),
                "ip": node.get("internal_ip"),
                "role": role,
                "status": node.get("status"),
                "version": node.get("version"),
                "os": node.get("os_image")
            })

        # Count by role
        server_count = sum(1 for n in nodes if n.get("role") == "server")
        agent_count = sum(1 for n in nodes if n.get("role") == "agent")

        return {
            "cluster_id": cluster.id,
            "cluster_name": cluster.name,
            "nodes": nodes,
            "summary": {
                "total": len(nodes),
                "servers": server_count,
                "agents": agent_count
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cluster nodes: {str(e)}")

@router.post("/{cluster_id}/scale/add")
async def add_nodes(
    cluster_id: int,
    nodes_to_add: dict,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Add new nodes to cluster

    Body:
        {
            "nodes": [
                {
                    "hostname": "worker-02",
                    "ip": "10.0.0.5",
                    "role": "agent"
                }
            ]
        }

    Returns job ID for tracking
    """
    from app.services.ansible_service import execute_add_nodes
    from app.services.cluster_cache_service import invalidate_cache
    from app.services.cluster_lock_service import (
        acquire_cluster_lock,
        check_bootstrap_prerequisite,
        check_node_identity,
        split_master_worker_additions
    )

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if cluster.cluster_type != ClusterType.NEW:
        raise HTTPException(status_code=400, detail="Can only scale 'new' type clusters")

    nodes = nodes_to_add.get("nodes", [])
    if not nodes:
        raise HTTPException(status_code=400, detail="No nodes provided")

    # Validate node data
    for node in nodes:
        if not all(k in node for k in ["hostname", "ip", "role"]):
            raise HTTPException(status_code=400, detail="Each node must have hostname, ip, and role")
        if node["role"] not in ["server", "agent"]:
            raise HTTPException(status_code=400, detail="Role must be 'server' or 'agent'")

    # G4: Check node identity (prevent duplicates)
    valid, error_msg = check_node_identity(db, cluster_id, nodes)
    if not valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # G3: Split master and worker additions if both present
    master_nodes, worker_nodes = split_master_worker_additions(nodes)

    if master_nodes and worker_nodes:
        # Both present - create two sequential jobs
        # First job: add masters
        job_masters = Job(
            cluster_id=cluster_id,
            job_type="add_nodes",
            status=JobStatus.PENDING
        )
        db.add(job_masters)
        db.commit()
        db.refresh(job_masters)

        try:
            acquire_cluster_lock(db, cluster_id, job_masters.id, "scale_add_masters")
        except HTTPException:
            db.delete(job_masters)
            db.commit()
            raise

        # Execute masters addition
        background_tasks.add_task(execute_add_nodes, job_masters.id, cluster_id, master_nodes)

        # Return info about sequencing
        return {
            "job_id": job_masters.id,
            "message": f"Adding {len(master_nodes)} master(s) first, then {len(worker_nodes)} worker(s) will be added automatically",
            "status": "pending",
            "sequenced": True,
            "workers_pending": len(worker_nodes)
        }
    else:
        # Only masters or only workers
        # G1: Check bootstrap prerequisite ONLY if:
        # - Adding workers (always need initial master)
        # - Adding joining masters (need initial master, not first master)
        # Skip check if this is the FIRST master being added
        has_initial_master = db.query(Node).filter(
            Node.cluster_id == cluster_id,
            Node.role == NodeRole.INITIAL_MASTER
        ).first() is not None

        adding_workers = worker_nodes and len(worker_nodes) > 0
        adding_joining_masters = master_nodes and len(master_nodes) > 0 and has_initial_master

        if adding_workers or adding_joining_masters:
            valid, error_msg = check_bootstrap_prerequisite(db, cluster_id)
            if not valid:
                raise HTTPException(status_code=400, detail=error_msg)

        # Create single job
        job = Job(
            cluster_id=cluster_id,
            job_type="add_nodes",
            status=JobStatus.PENDING
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        try:
            operation_type = "scale_add_masters" if master_nodes else "scale_add_workers"
            acquire_cluster_lock(db, cluster_id, job.id, operation_type)
        except HTTPException:
            db.delete(job)
            db.commit()
            raise

        # Execute in background
        background_tasks.add_task(execute_add_nodes, job.id, cluster_id, nodes)

        # Invalidate cache
        invalidate_cache(db, cluster_id)

        return {"job_id": job.id, "message": f"Adding {len(nodes)} node(s)", "status": "pending"}

@router.post("/{cluster_id}/scale/remove")
async def remove_nodes(
    cluster_id: int,
    nodes_to_remove: dict,
    background_tasks: BackgroundTasks,
    confirm_master_removal: bool = False,
    db: Session = Depends(get_db)
):
    """
    Remove nodes from cluster

    Body:
        {
            "nodes": [
                {
                    "hostname": "worker-02",
                    "ip": "10.0.0.5",
                    "role": "agent"
                }
            ]
        }

    Query params:
        confirm_master_removal: Required when removing control-plane nodes

    Returns job ID for tracking
    """
    from app.services.ansible_service import execute_remove_nodes
    from app.services.cluster_cache_service import invalidate_cache
    from app.services.cluster_lock_service import (
        acquire_cluster_lock,
        check_safe_master_removal
    )

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if cluster.cluster_type != ClusterType.NEW:
        raise HTTPException(status_code=400, detail="Can only scale 'new' type clusters")

    nodes = nodes_to_remove.get("nodes", [])
    if not nodes:
        raise HTTPException(status_code=400, detail="No nodes provided")

    # G2: Check safe master removal
    valid, error_msg = check_safe_master_removal(
        db,
        cluster_id,
        nodes,
        require_confirmation=not confirm_master_removal
    )
    if not valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Create job for tracking
    job = Job(
        cluster_id=cluster_id,
        job_type="remove_nodes",
        status=JobStatus.PENDING
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        # Acquire cluster lock
        acquire_cluster_lock(db, cluster_id, job.id, "scale_remove")
    except HTTPException:
        # Lock failed - clean up job
        db.delete(job)
        db.commit()
        raise

    # Execute in background (pass cluster_id instead of cluster object)
    background_tasks.add_task(execute_remove_nodes, job.id, cluster_id, nodes)

    # Invalidate cache
    invalidate_cache(db, cluster_id)

    return {"job_id": job.id, "message": f"Removing {len(nodes)} node(s)", "status": "pending"}


@router.post("/{cluster_id}/sync-nodes")
async def sync_cluster_nodes(
    cluster_id: int,
    db: Session = Depends(get_db)
):
    """
    Sync node statuses from Kubernetes cluster inspection to database.

    This updates database node statuses to match the actual cluster state.
    Useful when nodes show PENDING in DB but are actually ACTIVE in the cluster.

    Returns sync results including updated node count and details.
    """
    from app.services.node_sync_service import sync_node_statuses_from_inspection

    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    result = sync_node_statuses_from_inspection(db, cluster_id)

    if not result.get("synced") and result.get("errors"):
        raise HTTPException(status_code=400, detail=result["errors"][0])

    # Invalidate cache after sync
    invalidate_cache(db, cluster_id)

    return result
