"""
Pre-flight Check JSON Schema for LLM Analysis
Machine-readable output for upgrade readiness assessment
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    """Individual check result"""
    check_id: str = Field(..., description="Unique check identifier")
    category: str = Field(..., description="os|rke2|kubernetes|network|storage")
    severity: str = Field(..., description="OK|WARN|CRITICAL")
    message: str = Field(..., description="Human-readable summary")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Raw metrics for LLM")
    node_name: Optional[str] = Field(None, description="Node name if node-specific")


class NodeInfo(BaseModel):
    """Node-level information"""
    name: str
    role: str  # initial_master|master|worker
    ip: str
    os_version: str
    kernel_version: str
    disk_usage: Dict[str, Any]  # {"/var/lib/rancher": {"free_pct": 45, "inodes_free_pct": 80}}
    swap_enabled: bool
    memory: Dict[str, Any]  # {"total_mb": 8192, "used_mb": 4096, "oom_events_1h": 0}
    time_drift_ms: Optional[int]
    ntp_status: str  # synced|unsynced|unknown
    firewall_status: str  # disabled|enabled
    ports_reachable: Dict[int, bool]  # {9345: true, 6443: true}
    rke2_service_status: str  # active|inactive|failed


class EtcdHealth(BaseModel):
    """Etcd cluster health"""
    endpoint_health: Dict[str, str]  # {"node1": "healthy", "node2": "healthy"}
    leader_present: bool
    db_size_mb: float
    defrag_recommended: bool
    member_count: int


class CertificateInfo(BaseModel):
    """TLS certificate info"""
    path: str
    subject: str
    expiry_date: str  # ISO 8601
    days_until_expiry: int
    expired: bool


class KubernetesHealth(BaseModel):
    """Kubernetes layer health"""
    node_ready_count: int
    node_not_ready_count: int
    cordoned_nodes: List[str]
    kube_system_pod_restarts: Dict[str, int]  # {"coredns-xxx": 2, "etcd-xxx": 0}
    crash_loop_pods: List[str]
    image_pull_backoff_pods: List[str]
    deprecated_apis: List[Dict[str, str]]  # [{"api": "v1beta1/Ingress", "resource": "my-ingress"}]
    admission_webhooks: List[Dict[str, Any]]  # [{"name": "x", "type": "validating", "failurePolicy": "Fail"}]


class NetworkHealth(BaseModel):
    """Network layer health"""
    cni_type: str  # canal|cilium|calico
    cni_pods_running: int
    cni_pods_not_running: int
    pod_cidr: str
    pod_cidr_usage_pct: Optional[float]  # IP exhaustion risk
    ingress_controller: Optional[str]
    ingress_version: Optional[str]


class StorageHealth(BaseModel):
    """Storage layer health"""
    default_storageclass: Optional[str]
    provisioner_type: Optional[str]  # longhorn|local-path|nfs
    provisioner_pods_healthy: bool
    pvc_pending_count: int


class ClusterMetadata(BaseModel):
    """Cluster identification"""
    cluster_id: int
    cluster_name: str
    rke2_version: str
    kubernetes_version: str
    node_count: int
    collected_at: str  # ISO 8601 timestamp
    target_version: Optional[str] = None  # Target RKE2 version for upgrade compatibility checks


class PreflightReport(BaseModel):
    """Complete pre-flight check report for LLM analysis"""
    cluster_metadata: ClusterMetadata
    nodes: List[NodeInfo]
    checks: List[CheckResult]
    etcd: Optional[EtcdHealth]
    certificates: List[CertificateInfo]
    kubernetes: KubernetesHealth
    network: NetworkHealth
    storage: StorageHealth
    
    class Config:
        json_schema_extra = {
            "example": {
                "cluster_metadata": {
                    "cluster_id": 1,
                    "cluster_name": "prod-cluster-01",
                    "rke2_version": "v1.28.5+rke2r1",
                    "kubernetes_version": "v1.28.5",
                    "node_count": 5,
                    "collected_at": "2025-12-31T12:00:00Z"
                },
                "checks": [
                    {
                        "check_id": "disk_space_var_lib_rancher",
                        "category": "os",
                        "severity": "WARN",
                        "message": "Disk space below 30% on node master-01",
                        "raw_data": {"free_pct": 25, "free_gb": 15},
                        "node_name": "master-01"
                    }
                ]
            }
        }
