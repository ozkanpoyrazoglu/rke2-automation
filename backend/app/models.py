from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey, Enum, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database import Base

class ClusterType(str, enum.Enum):
    NEW = "new"
    REGISTERED = "registered"

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class CredentialType(str, enum.Enum):
    SSH_KEY = "ssh_key"
    SSH_PASSWORD = "ssh_password"

class NodeRole(str, enum.Enum):
    INITIAL_MASTER = "INITIAL_MASTER"
    MASTER = "MASTER"
    WORKER = "WORKER"

class NodeStatus(str, enum.Enum):
    PENDING = "PENDING"
    INSTALLING = "INSTALLING"
    ACTIVE = "ACTIVE"
    FAILED = "FAILED"
    DRAINING = "DRAINING"
    REMOVED = "REMOVED"

class Credential(Base):
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, nullable=False)
    credential_type = Column(Enum(CredentialType), nullable=False)

    # Encrypted credential data (private key or password)
    encrypted_secret = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    clusters = relationship("Cluster", back_populates="credential")

class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False)

    # Node identity
    hostname = Column(String, nullable=False)
    internal_ip = Column(String, nullable=False)
    external_ip = Column(String, nullable=True)

    # Role and status
    role = Column(Enum(NodeRole), nullable=False)
    status = Column(Enum(NodeStatus), default=NodeStatus.PENDING)

    # SSH connection preference
    use_external_ip = Column(Boolean, default=False)

    # Node-specific variables (JSON for flexibility)
    node_vars = Column(JSON, nullable=True)

    # Installation tracking
    installation_started_at = Column(DateTime, nullable=True)
    installation_completed_at = Column(DateTime, nullable=True)
    installation_error = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="cluster_nodes")

    # Constraints
    __table_args__ = (
        UniqueConstraint('cluster_id', 'hostname', name='uq_cluster_hostname'),
    )

    @property
    def ansible_ip(self):
        """IP to use for Ansible SSH connections"""
        return self.external_ip if self.use_external_ip and self.external_ip else self.internal_ip

class Cluster(Base):
    __tablename__ = "clusters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    cluster_type = Column(Enum(ClusterType), nullable=False)
    rke2_version = Column(String, nullable=False)

    # SSH credential reference
    credential_id = Column(Integer, ForeignKey("credentials.id"), nullable=True)

    # For new clusters
    registry_mode = Column(String, nullable=True)  # internet/airgap/custom
    custom_registry_url = Column(String, nullable=True)
    custom_config = Column(Text, nullable=True)  # YAML overrides

    # RKE2 configuration
    rke2_data_dir = Column(String, default="/var/lib/rancher/rke2")
    rke2_api_ip = Column(String, nullable=True)  # HA VIP or first master IP
    rke2_token = Column(String, nullable=True)  # Cluster join token
    rke2_additional_sans = Column(JSON, nullable=True)  # Additional SANs for API cert
    cni = Column(String, default="canal")  # CNI plugin: canal, calico, cilium, none
    custom_registry = Column(String, default="deactive")  # active/deactive
    custom_mirror = Column(String, default="deactive")  # active/deactive
    registry_address = Column(JSON, nullable=True)  # List of registry addresses
    registry_user = Column(String, nullable=True)
    registry_password = Column(String, nullable=True)

    # Custom container images (optional - for airgap/custom registry)
    kube_apiserver_image = Column(String, nullable=True)
    kube_controller_manager_image = Column(String, nullable=True)
    kube_proxy_image = Column(String, nullable=True)
    kube_scheduler_image = Column(String, nullable=True)
    pause_image = Column(String, nullable=True)
    runtime_image = Column(String, nullable=True)
    etcd_image = Column(String, nullable=True)

    # For registered clusters
    kubeconfig = Column(Text, nullable=True)

    # Installation state tracking
    installation_stage = Column(String, nullable=True)  # initial_master, joining_masters, workers, completed

    # Cluster-wide variables (Ansible extra vars)
    cluster_vars = Column(JSON, nullable=True)

    # Cluster operation lock (prevents concurrent operations)
    operation_status = Column(String, default="idle")  # idle|running
    current_job_id = Column(Integer, nullable=True)  # ID of running job
    operation_started_at = Column(DateTime, nullable=True)  # When current operation started
    operation_locked_by = Column(String, nullable=True)  # Operation type (install/scale_add/scale_remove/uninstall)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    jobs = relationship("Job", back_populates="cluster", cascade="all, delete-orphan")
    credential = relationship("Credential", back_populates="clusters")
    cluster_nodes = relationship("Node", back_populates="cluster", cascade="all, delete-orphan")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)
    job_type = Column(String, nullable=False)  # install, upgrade_check
    status = Column(Enum(JobStatus), default=JobStatus.PENDING, nullable=False)

    # Ansible execution details
    playbook_path = Column(String, nullable=True)
    inventory_path = Column(String, nullable=True)
    output = Column(Text, nullable=True)
    process_id = Column(Integer, nullable=True)  # Docker exec process PID

    # Upgrade check results
    readiness_json = Column(JSON, nullable=True)
    llm_summary = Column(Text, nullable=True)

    # LLM metrics tracking
    llm_model = Column(String, nullable=True)
    llm_token_count = Column(Integer, nullable=True)

    # Target RKE2 version for upgrade readiness checks
    target_version = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    cluster = relationship("Cluster", back_populates="jobs")

class ClusterStatusCache(Base):
    __tablename__ = "cluster_status_cache"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), unique=True, nullable=False)

    # Cached status data (aggregated LLM-ready format)
    cached_data = Column(JSON, nullable=False)

    # Cache metadata
    collected_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    collection_duration_seconds = Column(Integer, nullable=False)

    # Relationship
    cluster = relationship("Cluster")
