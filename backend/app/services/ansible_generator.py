from jinja2 import Template
from app.models import Cluster, NodeRole
import yaml
import secrets
import string

INVENTORY_TEMPLATE = """[masters]
{%- for node in nodes %}
{%- if node.role.value in ['INITIAL_MASTER', 'MASTER'] %}
{{ node.hostname }} ansible_host={{ node.ansible_ip }} ansible_user={{ username }}
{%- endif %}
{%- endfor %}

[workers]
{%- for node in nodes %}
{%- if node.role.value == 'WORKER' %}
{{ node.hostname }} ansible_host={{ node.ansible_ip }} ansible_user={{ username }}
{%- endif %}
{%- endfor %}

[k8s_cluster:children]
masters
workers
"""

def generate_token():
    """Generate a random token for RKE2 cluster"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(64))

def generate_ansible_artifacts(cluster: Cluster, output_dir: str):
    """
    Generate Ansible inventory and group_vars matching production structure
    Now uses cluster.cluster_nodes relationship instead of JSON
    """
    # Get username from credential
    username = cluster.credential.username if cluster.credential else "root"

    # Auto-generate token if not provided
    if not cluster.rke2_token:
        cluster.rke2_token = generate_token()

    # Auto-set API IP to first master if not provided
    if not cluster.rke2_api_ip:
        master_nodes = [node for node in cluster.cluster_nodes if node.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]]
        if master_nodes:
            cluster.rke2_api_ip = master_nodes[0].internal_ip

    # Generate inventory from Node objects
    inventory = Template(INVENTORY_TEMPLATE).render(
        nodes=cluster.cluster_nodes,
        username=username
    )

    with open(f"{output_dir}/inventory.ini", "w") as f:
        f.write(inventory)

    # Generate group_vars/k8s_cluster.yaml matching production structure
    group_vars = {
        "rke2_data_dir": cluster.rke2_data_dir,
        "rke2_api_ip": cluster.rke2_api_ip,
        "rke2_token": cluster.rke2_token,
        "rke2_version": cluster.rke2_version,
        "cni": cluster.cni,
        "custom_registry": cluster.custom_registry,
        "custom_mirror": cluster.custom_mirror,
    }

    # Add additional SANs
    if cluster.rke2_additional_sans:
        group_vars["rke2_additional_sans"] = cluster.rke2_additional_sans
    else:
        # Default: add all master IPs as SANs
        master_ips = [node.internal_ip for node in cluster.cluster_nodes if node.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]]
        group_vars["rke2_additional_sans"] = master_ips

    # Add registry configuration if custom mirror is active
    if cluster.custom_mirror == "active" and cluster.registry_address:
        group_vars["registry_address"] = cluster.registry_address
        group_vars["registry_user"] = cluster.registry_user
        group_vars["registry_password"] = cluster.registry_password

    # Add custom container images if provided
    if cluster.kube_apiserver_image:
        group_vars["kube_apiserver_image"] = cluster.kube_apiserver_image
    if cluster.kube_controller_manager_image:
        group_vars["kube_controller_manager_image"] = cluster.kube_controller_manager_image
    if cluster.kube_proxy_image:
        group_vars["kube_proxy_image"] = cluster.kube_proxy_image
    if cluster.kube_scheduler_image:
        group_vars["kube_scheduler_image"] = cluster.kube_scheduler_image
    if cluster.pause_image:
        group_vars["pause_image"] = cluster.pause_image
    if cluster.runtime_image:
        group_vars["runtime_image"] = cluster.runtime_image
    if cluster.etcd_image:
        group_vars["etcd_image"] = cluster.etcd_image

    # Create group_vars directory structure
    import os
    os.makedirs(f"{output_dir}/group_vars", exist_ok=True)
    os.makedirs(f"{output_dir}/host_vars", exist_ok=True)

    with open(f"{output_dir}/group_vars/k8s_cluster.yaml", "w") as f:
        yaml.dump(group_vars, f, default_flow_style=False)

    # Create group_vars for masters (rke2_type: server)
    masters_vars = {"rke2_type": "server"}
    with open(f"{output_dir}/group_vars/masters.yaml", "w") as f:
        yaml.dump(masters_vars, f, default_flow_style=False)

    # Create group_vars for workers (rke2_type: agent)
    workers_vars = {"rke2_type": "agent"}
    with open(f"{output_dir}/group_vars/workers.yaml", "w") as f:
        yaml.dump(workers_vars, f, default_flow_style=False)

    # Create host_vars for each node with role-specific information
    for node in cluster.cluster_nodes:
        host_vars = {
            "node_role": node.role.value,  # INITIAL_MASTER, MASTER, or WORKER
        }

        # Determine which config template to use based on role
        if node.role == NodeRole.INITIAL_MASTER:
            host_vars["config_template"] = "config_initial_master.yaml.j2"
        elif node.role == NodeRole.MASTER:
            host_vars["config_template"] = "config_joining_master.yaml.j2"
        elif node.role == NodeRole.WORKER:
            host_vars["config_template"] = "config_worker.yaml.j2"

        with open(f"{output_dir}/host_vars/{node.hostname}.yaml", "w") as f:
            yaml.dump(host_vars, f, default_flow_style=False)

    return output_dir
