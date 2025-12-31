"""
Dynamic Ansible Inventory Renderer

Generates Ansible inventory from database instead of static files.
Supports stage-specific rendering for proper RKE2 installation ordering.
"""

from typing import List, Optional
from app.models import Cluster, Node, NodeRole, NodeStatus


class InventoryRenderer:
    """
    Generates Ansible inventory dynamically from database
    Supports stage-specific inventory generation
    """

    @staticmethod
    def render_for_stage(cluster: Cluster, stage: str, nodes: Optional[List[Node]] = None) -> str:
        """
        Render inventory for specific installation stage

        Args:
            cluster: Cluster object
            stage: "initial_master", "joining_masters", "workers", "all"
            nodes: Specific nodes to include (for scale operations)

        Returns:
            Ansible inventory content (INI format)
        """
        if nodes is None:
            nodes = cluster.cluster_nodes

        # Filter nodes based on stage and status
        if stage == "initial_master":
            target_nodes = [n for n in nodes if n.role == NodeRole.INITIAL_MASTER and n.status != NodeStatus.REMOVED]
        elif stage == "joining_masters":
            target_nodes = [n for n in nodes if n.role == NodeRole.MASTER and n.status != NodeStatus.REMOVED]
        elif stage == "workers":
            target_nodes = [n for n in nodes if n.role == NodeRole.WORKER and n.status != NodeStatus.REMOVED]
        elif stage == "all":
            target_nodes = [n for n in nodes if n.status != NodeStatus.REMOVED]
        else:
            raise ValueError(f"Unknown stage: {stage}")

        # Render inventory
        return InventoryRenderer._render_inventory(cluster, target_nodes, stage)

    @staticmethod
    def _render_inventory(cluster: Cluster, nodes: List[Node], stage: str) -> str:
        """Internal inventory rendering"""

        # Get username from credential
        username = cluster.credential.username if cluster.credential else "root"

        inventory_lines = []

        # Stage-specific groups
        if stage == "initial_master":
            inventory_lines.append("[initial_master]")
            for node in nodes:
                inventory_lines.append(
                    f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role=initial_master"
                )

        elif stage == "joining_masters":
            inventory_lines.append("[joining_masters]")
            for node in nodes:
                inventory_lines.append(
                    f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role=joining_master"
                )

        elif stage == "workers":
            inventory_lines.append("[workers]")
            for node in nodes:
                inventory_lines.append(
                    f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=agent node_role=worker"
                )

        elif stage == "all":
            # Traditional masters/workers groups
            masters = [n for n in nodes if n.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]]
            workers = [n for n in nodes if n.role == NodeRole.WORKER]

            inventory_lines.append("[masters]")
            for node in masters:
                role_var = "initial_master" if node.role == NodeRole.INITIAL_MASTER else "joining_master"
                inventory_lines.append(
                    f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role={role_var}"
                )

            inventory_lines.append("\n[workers]")
            for node in workers:
                inventory_lines.append(
                    f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=agent node_role=worker"
                )

            inventory_lines.append("\n[k8s_cluster:children]")
            inventory_lines.append("masters")
            inventory_lines.append("workers")

        return "\n".join(inventory_lines)

    @staticmethod
    def render_for_scale_add(cluster: Cluster, new_nodes: List[Node]) -> str:
        """
        Render inventory for adding nodes to existing cluster
        All new nodes join an existing cluster, so they need server: parameter
        """
        username = cluster.credential.username if cluster.credential else "root"

        inventory_lines = []
        inventory_lines.append("[new_nodes]")

        servers = []
        agents = []

        for node in new_nodes:
            if node.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]:
                # When adding to existing cluster, all servers are "joining"
                servers.append(node)
                inventory_lines.append(
                    f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role=joining_master"
                )
            else:
                agents.append(node)
                inventory_lines.append(
                    f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=agent node_role=worker"
                )

        inventory_lines.append("\n[new_servers]")
        for node in servers:
            inventory_lines.append(node.hostname)

        inventory_lines.append("\n[new_agents]")
        for node in agents:
            inventory_lines.append(node.hostname)

        return "\n".join(inventory_lines)
