"""
Ansible Variable Renderer

Renders Ansible variables from cluster and node configuration.
"""

from typing import Dict, Any
from app.models import Cluster, Node


class VariableRenderer:
    """
    Renders Ansible variables from cluster and node configuration
    """

    @staticmethod
    def render_cluster_vars(cluster: Cluster) -> Dict[str, Any]:
        """
        Render cluster-wide Ansible variables
        These become group_vars/all.yaml or extra vars
        """
        vars_dict = {
            "rke2_version": cluster.rke2_version,
            "rke2_data_dir": cluster.rke2_data_dir,
            "rke2_api_ip": cluster.rke2_api_ip,
            "rke2_token": cluster.rke2_token,
            "cni": cluster.cni or "canal",
            "custom_registry": cluster.custom_registry or "deactive",
            "custom_mirror": cluster.custom_mirror or "deactive",
        }

        # Add optional fields
        if cluster.rke2_additional_sans:
            vars_dict["rke2_additional_sans"] = cluster.rke2_additional_sans

        if cluster.custom_mirror == "active" and cluster.registry_address:
            vars_dict["registry_address"] = cluster.registry_address
            vars_dict["registry_user"] = cluster.registry_user or ""
            vars_dict["registry_password"] = cluster.registry_password or ""

        # Custom container images
        image_fields = [
            "kube_apiserver_image", "kube_controller_manager_image",
            "kube_proxy_image", "kube_scheduler_image",
            "pause_image", "runtime_image", "etcd_image"
        ]
        for field in image_fields:
            value = getattr(cluster, field, None)
            if value:
                vars_dict[field] = value

        # Merge cluster_vars JSON if present
        if cluster.cluster_vars:
            vars_dict.update(cluster.cluster_vars)

        return vars_dict

    @staticmethod
    def render_node_vars(node: Node) -> Dict[str, Any]:
        """
        Render node-specific variables
        """
        vars_dict = {
            "node_hostname": node.hostname,
            "node_internal_ip": node.internal_ip,
            "node_role": node.role.value,
        }

        if node.external_ip:
            vars_dict["node_external_ip"] = node.external_ip

        # Merge node_vars JSON if present
        if node.node_vars:
            vars_dict.update(node.node_vars)

        return vars_dict
