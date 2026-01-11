"""
Preflight Background Service
Runs preflight checks asynchronously in a background thread
"""

import json
import logging
from datetime import datetime

from app.database import SessionLocal
from app.models import Job, JobStatus, Cluster, CredentialType
from app.services.preflight.collector import PreflightCollector
from app.services.bedrock_deepseek import DeepSeekBedrockAnalyzer
from app.services.encryption_service import decrypt_secret

logger = logging.getLogger(__name__)


def run_preflight_check_background(job_id: int, analyze: bool = False, target_version: str = None):
    """
    Run preflight check in background thread

    Args:
        job_id: ID of the job to execute
        analyze: Whether to run AI analysis on the results
        target_version: Target RKE2 version for upgrade compatibility checks (optional)
    """
    db = SessionLocal()

    try:
        # Get job from database
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        # Get cluster
        cluster = db.query(Cluster).filter(Cluster.id == job.cluster_id).first()
        if not cluster:
            logger.error(f"Cluster {job.cluster_id} not found for job {job_id}")
            job.status = JobStatus.FAILED
            job.output = "Cluster not found"
            job.completed_at = datetime.utcnow()
            db.commit()
            return

        # Update job status to RUNNING
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        logger.info(f"Starting preflight check for cluster {cluster.name} (job {job_id})")

        # Validate kubeconfig exists
        if not cluster.kubeconfig:
            raise ValueError("Cluster does not have kubeconfig configured")

        # Get cluster credential for SSH access
        credential = cluster.credential
        if not credential:
            raise ValueError("Cluster does not have credential configured")

        # Get all nodes for this cluster
        nodes = cluster.cluster_nodes
        if not nodes:
            raise ValueError("Cluster has no nodes configured")

        # Decrypt credential secret
        decrypted_secret = decrypt_secret(credential.encrypted_secret)

        # Prepare node data for collector
        node_data = []
        for node in nodes:
            # Use external_ip if flag is set and external_ip exists, otherwise use internal_ip
            ip_address = node.external_ip if (node.use_external_ip and node.external_ip) else node.internal_ip

            # Build node info based on credential type
            node_info = {
                "hostname": node.hostname,
                "ip": ip_address,
                "role": node.role.value,  # Convert enum to string
                "ssh_user": credential.username,
            }

            # Add credential based on type
            if credential.credential_type == CredentialType.SSH_KEY:
                node_info["ssh_key"] = decrypted_secret
                node_info["ssh_password"] = None
            else:  # SSH_PASSWORD
                node_info["ssh_password"] = decrypted_secret
                node_info["ssh_key"] = None

            node_data.append(node_info)

        # Initialize PreflightCollector
        collector = PreflightCollector(
            cluster_id=cluster.id,
            cluster_name=cluster.name,
            kubeconfig=cluster.kubeconfig,
            target_version=target_version
        )

        # Generate preflight report
        logger.info(f"Collecting preflight data for job {job_id}")
        report = collector.generate_report(node_data)

        # Convert Pydantic model to dict for storage (Pydantic v2)
        report_dict = report.model_dump()

        # Store raw preflight data in job
        job.readiness_json = report_dict

        # Run AI analysis if requested
        if analyze:
            logger.info(f"Running AI analysis for job {job_id}")
            try:
                analyzer = DeepSeekBedrockAnalyzer()
                analysis_result, model_id, token_count = analyzer.analyze(report_dict)

                # Store analysis result as JSON string (Pydantic v2)
                job.llm_summary = json.dumps(analysis_result.model_dump())
                job.llm_model = model_id
                job.llm_token_count = token_count

                logger.info(f"AI analysis completed: verdict={analysis_result.verdict}, "
                           f"model={model_id}, tokens={token_count}")

            except Exception as e:
                logger.error(f"AI analysis failed for job {job_id}: {str(e)}")
                # Continue - don't fail the whole job if only AI analysis fails
                job.output = f"Preflight check completed but AI analysis failed: {str(e)}"

        # Mark job as successful
        job.status = JobStatus.SUCCESS
        job.completed_at = datetime.utcnow()

        if not job.output:
            job.output = "Preflight check completed successfully"

        db.commit()
        logger.info(f"Preflight check completed for job {job_id}")

    except Exception as e:
        logger.error(f"Preflight check failed for job {job_id}: {str(e)}", exc_info=True)

        # Mark job as failed
        job.status = JobStatus.FAILED
        job.completed_at = datetime.utcnow()
        job.output = f"Preflight check failed: {str(e)}"
        db.commit()

    finally:
        db.close()
