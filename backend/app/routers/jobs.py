from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from sse_starlette.sse import EventSourceResponse
from app.database import get_db
from app.models import Cluster, Job, JobStatus
from app.schemas import JobResponse, JobDetail, UpgradeReadinessRequest
from app.services.ansible_service import execute_install_playbook, execute_uninstall_playbook
from app.services.readiness_service import run_upgrade_readiness_check
from app.services.cluster_lock_service import acquire_cluster_lock, release_cluster_lock

router = APIRouter()

@router.post("/install/{cluster_id}", response_model=JobResponse)
async def install_cluster(
    cluster_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Execute RKE2 installation playbook for a cluster"""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if cluster.cluster_type != "new":
        raise HTTPException(status_code=400, detail="Can only install new clusters")

    # Create job first (need job_id for lock)
    job = Job(cluster_id=cluster_id, job_type="install", status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        # Acquire cluster lock
        acquire_cluster_lock(db, cluster_id, job.id, "install")
    except HTTPException:
        # Lock failed - clean up job
        db.delete(job)
        db.commit()
        raise

    # Execute in background
    background_tasks.add_task(execute_install_playbook, job.id)

    return job

@router.post("/upgrade-check", response_model=JobResponse)
async def check_upgrade_readiness(
    request: UpgradeReadinessRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Run upgrade readiness check on a registered cluster"""
    cluster = db.query(Cluster).filter(Cluster.id == request.cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if cluster.cluster_type != "registered":
        raise HTTPException(status_code=400, detail="Can only check registered clusters")

    # Create job
    job = Job(
        cluster_id=cluster.id,
        job_type="upgrade_check",
        status=JobStatus.PENDING
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Execute in background
    background_tasks.add_task(run_upgrade_readiness_check, job.id)

    return job

@router.post("/uninstall/{cluster_id}", response_model=JobResponse)
async def uninstall_cluster(
    cluster_id: int,
    confirmation: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Uninstall RKE2 from all cluster nodes - requires confirmation"""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    if cluster.cluster_type != "new":
        raise HTTPException(status_code=400, detail="Can only uninstall new clusters")

    # Require exact cluster name confirmation
    if confirmation != cluster.name:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation failed. Please type the exact cluster name: {cluster.name}"
        )

    # Create job first (need job_id for lock)
    job = Job(cluster_id=cluster_id, job_type="uninstall", status=JobStatus.PENDING)
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        # Acquire cluster lock
        acquire_cluster_lock(db, cluster_id, job.id, "uninstall")
    except HTTPException:
        # Lock failed - clean up job
        db.delete(job)
        db.commit()
        raise

    # Execute in background
    background_tasks.add_task(execute_uninstall_playbook, job.id)

    return job

@router.get("", response_model=List[JobResponse])
async def list_jobs(
    cluster_id: int = None,
    db: Session = Depends(get_db)
):
    """List all jobs, optionally filtered by cluster"""
    query = db.query(Job)
    if cluster_id:
        query = query.filter(Job.cluster_id == cluster_id)

    jobs = query.order_by(Job.created_at.desc()).all()
    return jobs

@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: int, db: Session = Depends(get_db)):
    """Get job details including output"""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/{job_id}/terminate")
async def terminate_job(job_id: int, db: Session = Depends(get_db)):
    """Terminate a running job"""
    import signal
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Job is not running")

    if not job.process_id:
        raise HTTPException(status_code=400, detail="No process ID found for job")

    try:
        # Kill the process
        import os
        os.kill(job.process_id, signal.SIGTERM)

        # Update job status
        job.status = JobStatus.FAILED
        job.output = (job.output or "") + "\n\n[Job terminated by user]"
        from datetime import datetime
        job.completed_at = datetime.utcnow()
        db.commit()

        return {"message": f"Job {job_id} terminated successfully"}
    except ProcessLookupError:
        raise HTTPException(status_code=404, detail="Process not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to terminate job: {str(e)}")

@router.get("/{job_id}/stream")
async def stream_job_output(job_id: int):
    """Stream job output via SSE"""
    # Verify job exists
    from app.database import SessionLocal
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        # Simple polling implementation - in production use proper event system
        import asyncio
        last_length = 0

        while True:
            # Create a new session for each query to avoid detached instance errors
            with SessionLocal() as db:
                job = db.query(Job).filter(Job.id == job_id).first()
                if not job:
                    break

                if job.output and len(job.output) > last_length:
                    new_output = job.output[last_length:]
                    yield {"data": new_output}
                    last_length = len(job.output)

                if job.status in [JobStatus.SUCCESS, JobStatus.FAILED]:
                    yield {"data": f"\n[Job {job.status.value}]"}
                    break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())
