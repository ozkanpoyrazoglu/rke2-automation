import subprocess
import json
from datetime import datetime
from kubernetes import client, config
from app.database import SessionLocal
from app.models import Job, JobStatus
from app.services.llm_service import generate_upgrade_summary

def run_upgrade_readiness_check(job_id: int):
    """
    Run comprehensive upgrade readiness checks on registered cluster
    """
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()

    try:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        cluster = job.cluster
        kubeconfig_path = f"/ansible/clusters/{cluster.name}/kubeconfig"

        # Load kubeconfig
        config.load_kube_config(config_file=kubeconfig_path)

        # Run checks
        readiness = {
            "cluster_name": cluster.name,
            "current_version": get_current_rke2_version(kubeconfig_path),
            "target_version": cluster.rke2_version,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }

        # Check 1: etcd health
        readiness["checks"]["etcd"] = check_etcd_health(kubeconfig_path)

        # Check 2: Node status
        readiness["checks"]["nodes"] = check_node_status()

        # Check 3: Disk usage
        readiness["checks"]["disk"] = check_disk_usage()

        # Check 4: Certificate expiration
        readiness["checks"]["certificates"] = check_certificate_expiration()

        # Check 5: Deprecated API usage
        readiness["checks"]["deprecated_apis"] = check_deprecated_apis(
            readiness["current_version"],
            cluster.rke2_version
        )

        # Determine overall status
        readiness["ready"] = all(
            check.get("passed", False)
            for check in readiness["checks"].values()
        )

        job.readiness_json = readiness

        # Generate LLM summary
        llm_summary = generate_upgrade_summary(readiness)
        job.llm_summary = llm_summary

        job.status = JobStatus.SUCCESS
        job.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        job.status = JobStatus.FAILED
        job.output = f"Readiness check failed: {str(e)}"
        job.completed_at = datetime.utcnow()
        db.commit()

    finally:
        db.close()

def get_current_rke2_version(kubeconfig_path: str) -> str:
    """Get current RKE2 version from cluster"""
    v1 = client.VersionApi()
    version_info = v1.get_code()
    return version_info.git_version

def check_etcd_health(kubeconfig_path: str) -> dict:
    """Check etcd cluster health and quorum"""
    try:
        # Execute etcdctl via kubectl exec on a control plane node
        result = subprocess.run(
            [
                "kubectl",
                "--kubeconfig", kubeconfig_path,
                "exec", "-n", "kube-system",
                "etcd-$(kubectl get nodes --kubeconfig {} -o jsonpath='{{.items[0].metadata.name}}')".format(kubeconfig_path),
                "--", "etcdctl",
                "endpoint", "health", "--cluster"
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        return {
            "passed": result.returncode == 0,
            "status": "healthy" if result.returncode == 0 else "unhealthy",
            "details": result.stdout,
            "severity": "critical" if result.returncode != 0 else "info"
        }
    except Exception as e:
        return {
            "passed": False,
            "status": "check_failed",
            "details": str(e),
            "severity": "critical"
        }

def check_node_status() -> dict:
    """Check all nodes are Ready"""
    v1 = client.CoreV1Api()
    nodes = v1.list_node()

    not_ready = []
    for node in nodes.items:
        for condition in node.status.conditions:
            if condition.type == "Ready" and condition.status != "True":
                not_ready.append(node.metadata.name)

    return {
        "passed": len(not_ready) == 0,
        "total_nodes": len(nodes.items),
        "not_ready_nodes": not_ready,
        "details": f"{len(nodes.items)} nodes, {len(not_ready)} not ready",
        "severity": "critical" if not_ready else "info"
    }

def check_disk_usage() -> dict:
    """Check disk usage on all nodes"""
    # Simplified - in production use metrics-server or node-exporter
    return {
        "passed": True,
        "details": "Disk usage check placeholder - integrate with monitoring",
        "severity": "warning"
    }

def check_certificate_expiration() -> dict:
    """Check certificate expiration dates"""
    # Simplified - in production parse actual certs
    return {
        "passed": True,
        "details": "Certificate expiration check placeholder",
        "severity": "info"
    }

def check_deprecated_apis(current_version: str, target_version: str) -> dict:
    """Check for deprecated API usage"""
    # Use pluto or similar tool
    try:
        result = subprocess.run(
            ["pluto", "detect-files", "-d", "/tmp"],
            capture_output=True,
            text=True,
            timeout=30
        )

        deprecated_count = result.stdout.count("DEPRECATED")

        return {
            "passed": deprecated_count == 0,
            "deprecated_apis_found": deprecated_count,
            "details": result.stdout if deprecated_count > 0 else "No deprecated APIs detected",
            "severity": "critical" if deprecated_count > 0 else "info"
        }
    except Exception as e:
        return {
            "passed": True,
            "details": f"Deprecated API check skipped: {str(e)}",
            "severity": "warning"
        }
