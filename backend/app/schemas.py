from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.models import ClusterType, JobStatus, CredentialType, NodeRole, NodeStatus

# Credential schemas
class CredentialCreate(BaseModel):
    name: str
    username: str
    credential_type: CredentialType
    secret: str  # SSH private key or password (plaintext, will be encrypted)

class CredentialResponse(BaseModel):
    id: int
    name: str
    username: str
    credential_type: CredentialType
    created_at: datetime

    class Config:
        from_attributes = True

# Access check schemas
class HostInput(BaseModel):
    hostname: str
    ip: str

class AccessCheckRequest(BaseModel):
    credential_id: int
    hosts: List[HostInput]

class HostCheckResult(BaseModel):
    hostname: str
    ip: str
    status: str  # ok / failed
    ssh_reachable: bool
    sudo_available: bool
    os_compatible: bool
    error: Optional[str] = None

class AccessCheckResponse(BaseModel):
    overall_status: str  # success / failed
    results: List[HostCheckResult]

# Node schemas
class NodeInput(BaseModel):
    hostname: str
    ip: str
    role: str = Field(..., pattern="^(server|agent)$")
    internal_ip: Optional[str] = None
    external_ip: Optional[str] = None
    use_external_ip: Optional[bool] = False

class NodeResponse(BaseModel):
    id: int
    hostname: str
    internal_ip: str
    external_ip: Optional[str] = None
    role: NodeRole
    status: NodeStatus
    use_external_ip: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

# Cluster schemas
class ClusterCreateNew(BaseModel):
    name: str
    rke2_version: str
    credential_id: int
    nodes: List[NodeInput]
    registry_mode: str = Field(..., pattern="^(internet|airgap|custom)$")
    custom_registry_url: Optional[str] = None
    custom_config: Optional[str] = None

    # RKE2 configuration
    rke2_data_dir: str = "/var/lib/rancher/rke2"
    rke2_api_ip: Optional[str] = None  # Will auto-set to first master if not provided
    rke2_token: Optional[str] = None  # Will auto-generate if not provided
    rke2_additional_sans: Optional[List[str]] = None
    cni: str = "canal"  # CNI plugin: canal, calico, cilium, none
    custom_registry: str = "deactive"
    custom_mirror: str = "deactive"
    registry_address: Optional[List[str]] = None
    registry_user: Optional[str] = None
    registry_password: Optional[str] = None

    # Custom container images (optional)
    kube_apiserver_image: Optional[str] = None
    kube_controller_manager_image: Optional[str] = None
    kube_proxy_image: Optional[str] = None
    kube_scheduler_image: Optional[str] = None
    pause_image: Optional[str] = None
    runtime_image: Optional[str] = None
    etcd_image: Optional[str] = None

class ClusterCreateRegistered(BaseModel):
    name: str
    kubeconfig: str
    target_rke2_version: str

class ClusterResponse(BaseModel):
    id: int
    name: str
    cluster_type: ClusterType
    rke2_version: str
    created_at: datetime
    kubeconfig: Optional[str] = None
    cluster_nodes: Optional[List[NodeResponse]] = None
    cni: Optional[str] = None
    rke2_data_dir: Optional[str] = None
    rke2_api_ip: Optional[str] = None
    rke2_token: Optional[str] = None
    rke2_additional_sans: Optional[List[str]] = None
    installation_stage: Optional[str] = None

    # Operation lock status
    operation_status: Optional[str] = "idle"
    current_job_id: Optional[int] = None
    operation_locked_by: Optional[str] = None

    class Config:
        from_attributes = True

# Job schemas
class JobResponse(BaseModel):
    id: int
    cluster_id: int
    job_type: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    llm_summary: Optional[str]
    llm_model: Optional[str] = None
    llm_token_count: Optional[int] = None
    target_version: Optional[str] = None

    class Config:
        from_attributes = True

class JobDetail(JobResponse):
    output: Optional[str]
    readiness_json: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True

# Upgrade readiness
class UpgradeReadinessRequest(BaseModel):
    cluster_id: int
