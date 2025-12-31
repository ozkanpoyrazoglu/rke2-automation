from sqlalchemy.orm import Session
from app.models import Cluster, ClusterType, Node, NodeRole, NodeStatus
from app.schemas import ClusterCreateNew, ClusterCreateRegistered
from app.services.ansible_generator import generate_ansible_artifacts
import os

def create_new_cluster(db: Session, cluster_data: ClusterCreateNew) -> Cluster:
    """
    Create new cluster and generate Ansible artifacts
    Now creates Node records instead of JSON
    """
    # Auto-populate rke2_api_ip if not provided (use first server node IP)
    api_ip = cluster_data.rke2_api_ip
    if not api_ip:
        server_nodes = [node for node in cluster_data.nodes if node.role == "server"]
        if server_nodes:
            api_ip = server_nodes[0].ip

    # Generate random token if not provided
    token = cluster_data.rke2_token
    if not token:
        import secrets
        token = secrets.token_urlsafe(32)

    # Create cluster without nodes
    cluster = Cluster(
        name=cluster_data.name,
        cluster_type=ClusterType.NEW,
        rke2_version=cluster_data.rke2_version,
        credential_id=cluster_data.credential_id,
        registry_mode=cluster_data.registry_mode,
        custom_registry_url=cluster_data.custom_registry_url,
        custom_config=cluster_data.custom_config,
        # RKE2 configuration
        rke2_data_dir=cluster_data.rke2_data_dir,
        rke2_api_ip=api_ip,
        rke2_token=token,
        rke2_additional_sans=cluster_data.rke2_additional_sans,
        cni=cluster_data.cni,
        custom_registry=cluster_data.custom_registry,
        custom_mirror=cluster_data.custom_mirror,
        registry_address=cluster_data.registry_address,
        registry_user=cluster_data.registry_user,
        registry_password=cluster_data.registry_password,
        # Custom images
        kube_apiserver_image=cluster_data.kube_apiserver_image,
        kube_controller_manager_image=cluster_data.kube_controller_manager_image,
        kube_proxy_image=cluster_data.kube_proxy_image,
        kube_scheduler_image=cluster_data.kube_scheduler_image,
        pause_image=cluster_data.pause_image,
        runtime_image=cluster_data.runtime_image,
        etcd_image=cluster_data.etcd_image
    )

    db.add(cluster)
    db.commit()
    db.refresh(cluster)

    # Create Node records
    first_server = True
    for node_data in cluster_data.nodes:
        # Determine node role
        if node_data.role == "server":
            role = NodeRole.INITIAL_MASTER if first_server else NodeRole.MASTER
            first_server = False
        else:
            role = NodeRole.WORKER

        # Extract IPs - use internal_ip if provided, otherwise fall back to ip
        internal_ip = getattr(node_data, 'internal_ip', None) or node_data.ip
        external_ip = getattr(node_data, 'external_ip', None)
        use_external_ip = getattr(node_data, 'use_external_ip', False)

        node = Node(
            cluster_id=cluster.id,
            hostname=node_data.hostname,
            internal_ip=internal_ip,
            external_ip=external_ip,
            role=role,
            status=NodeStatus.PENDING,
            use_external_ip=use_external_ip
        )
        db.add(node)

    db.commit()

    # Force refresh to load cluster_nodes relationship
    db.expire_all()
    db.refresh(cluster)

    # Generate Ansible inventory and playbooks
    artifacts_dir = f"/ansible/clusters/{cluster.name}"
    os.makedirs(artifacts_dir, exist_ok=True)

    generate_ansible_artifacts(cluster, artifacts_dir)

    return cluster

def register_cluster(db: Session, cluster_data: ClusterCreateRegistered) -> Cluster:
    """
    Register existing cluster via kubeconfig
    """
    cluster = Cluster(
        name=cluster_data.name,
        cluster_type=ClusterType.REGISTERED,
        rke2_version=cluster_data.target_rke2_version,
        kubeconfig=cluster_data.kubeconfig
    )

    db.add(cluster)
    db.commit()
    db.refresh(cluster)

    # Save kubeconfig to filesystem
    kubeconfig_dir = f"/ansible/clusters/{cluster.name}"
    os.makedirs(kubeconfig_dir, exist_ok=True)

    with open(f"{kubeconfig_dir}/kubeconfig", "w") as f:
        f.write(cluster.kubeconfig)

    return cluster
