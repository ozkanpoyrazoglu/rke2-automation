# RKE2 Hybrid Inventory Architecture

## Executive Summary

This document describes the redesigned architecture for RKE2 cluster installation and lifecycle management, addressing critical issues with the current static inventory approach.

**Key Problems Solved:**
1. Proper RKE2 installation stage ordering (initial master → additional masters → workers)
2. Dynamic node management for both new and registered clusters
3. Database as source of truth instead of static Ansible inventory files
4. Safe scale operations that maintain cluster quorum

---

## 1. Architecture Overview

### Current Problems

**Static Inventory Issues:**
- `cluster.nodes` JSON field is unreliable (mutable tracking issues)
- Registered clusters have no inventory source
- Scale operations don't update main inventory consistently
- No enforcement of RKE2 installation stage ordering
- Config templates don't distinguish initial master vs joining master

**Installation Stage Violations:**
- Current `install_rke2.yml` treats all masters equally
- No distinction between initial master (no `server:` param) and joining masters (requires `server:` param)
- Workers can be installed before all masters are ready
- No validation of cluster prerequisites

### Solution: Hybrid Model

**Database-First Approach:**
```
┌─────────────────────────────────────────────────────┐
│                    PostgreSQL                        │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │  Clusters  │  │   Nodes    │  │ Credentials  │  │
│  └────────────┘  └────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────┘
                         ▲
                         │ Query at runtime
                         │
┌─────────────────────────────────────────────────────┐
│            Inventory Renderer Service               │
│  • Reads from database                              │
│  • Generates ephemeral inventory                    │
│  • Stage-aware role assignment                      │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│          Stage Orchestrator                         │
│  • Enforces installation order                      │
│  • Validates prerequisites                          │
│  • Calls stage-specific playbooks                   │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│       Stage-Specific Playbooks                      │
│  • install_initial_master.yml                       │
│  • install_joining_masters.yml                      │
│  • install_workers.yml                              │
└─────────────────────────────────────────────────────┘
```

---

## 2. Database Schema Changes

### New Node Model

```python
class NodeRole(str, enum.Enum):
    INITIAL_MASTER = "initial_master"  # First server node
    MASTER = "master"                   # Joining server nodes
    WORKER = "worker"                   # Agent nodes

class NodeStatus(str, enum.Enum):
    PENDING = "pending"           # Not yet installed
    INSTALLING = "installing"     # Installation in progress
    ACTIVE = "active"             # Successfully joined cluster
    FAILED = "failed"             # Installation failed
    DRAINING = "draining"         # Being removed
    REMOVED = "removed"           # Removed from cluster

class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    cluster_id = Column(Integer, ForeignKey("clusters.id"), nullable=False)

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
    # Example: {"labels": {"env": "prod"}, "taints": [...]}
    node_vars = Column(JSON, nullable=True)

    # Installation tracking
    installation_started_at = Column(DateTime, nullable=True)
    installation_completed_at = Column(DateTime, nullable=True)
    installation_error = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    cluster = relationship("Cluster", back_populates="nodes")

    # Constraints
    __table_args__ = (
        UniqueConstraint('cluster_id', 'hostname', name='uq_cluster_hostname'),
    )

    @property
    def ansible_ip(self):
        """IP to use for Ansible SSH connections"""
        return self.external_ip if self.use_external_ip and self.external_ip else self.internal_ip
```

### Updated Cluster Model

```python
class Cluster(Base):
    __tablename__ = "clusters"

    # ... existing fields ...

    # REMOVE: nodes = Column(JSON, nullable=True)
    # REPLACE WITH: relationship
    nodes = relationship("Node", back_populates="cluster", cascade="all, delete-orphan")

    # Add cluster-wide variables
    cluster_vars = Column(JSON, nullable=True)  # Ansible extra vars

    # Installation state tracking
    installation_stage = Column(String, nullable=True)  # initial_master, joining_masters, workers, completed
```

### Migration Strategy

```python
# Alembic migration to convert existing JSON nodes to Node records

def upgrade():
    # Create nodes table
    op.create_table('nodes', ...)

    # Migrate existing cluster.nodes JSON to Node records
    connection = op.get_bind()
    clusters = connection.execute("SELECT id, name, nodes FROM clusters WHERE nodes IS NOT NULL")

    for cluster in clusters:
        if cluster.nodes:
            nodes_data = json.loads(cluster.nodes) if isinstance(cluster.nodes, str) else cluster.nodes

            # First server becomes initial_master
            first_server = True

            for node_data in nodes_data:
                role = NodeRole.INITIAL_MASTER if (node_data['role'] == 'server' and first_server) else \
                       NodeRole.MASTER if node_data['role'] == 'server' else \
                       NodeRole.WORKER

                if node_data['role'] == 'server':
                    first_server = False

                op.execute(f"""
                    INSERT INTO nodes (cluster_id, hostname, internal_ip, role, status)
                    VALUES ({cluster.id}, '{node_data['hostname']}', '{node_data['ip']}', '{role.value}', 'active')
                """)

    # Drop old nodes JSON column
    op.drop_column('clusters', 'nodes')

def downgrade():
    # Add back nodes column
    op.add_column('clusters', Column('nodes', JSON, nullable=True))

    # Convert Node records back to JSON
    # ... reverse migration ...

    # Drop nodes table
    op.drop_table('nodes')
```

---

## 3. Dynamic Inventory Renderer

### Inventory Renderer Service

```python
# backend/app/services/inventory_renderer.py

from typing import List, Dict, Optional
from app.models import Cluster, Node, NodeRole, NodeStatus
from jinja2 import Template

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
            nodes = cluster.nodes

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
                inventory_lines.append(f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role=initial_master")

        elif stage == "joining_masters":
            inventory_lines.append("[joining_masters]")
            for node in nodes:
                inventory_lines.append(f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role=joining_master")

        elif stage == "workers":
            inventory_lines.append("[workers]")
            for node in nodes:
                inventory_lines.append(f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=agent node_role=worker")

        elif stage == "all":
            # Traditional masters/workers groups
            masters = [n for n in nodes if n.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]]
            workers = [n for n in nodes if n.role == NodeRole.WORKER]

            inventory_lines.append("[masters]")
            for node in masters:
                role_var = "initial_master" if node.role == NodeRole.INITIAL_MASTER else "joining_master"
                inventory_lines.append(f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role={role_var}")

            inventory_lines.append("\n[workers]")
            for node in workers:
                inventory_lines.append(f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=agent node_role=worker")

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
                inventory_lines.append(f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=server node_role=joining_master")
            else:
                agents.append(node)
                inventory_lines.append(f"{node.hostname} ansible_host={node.ansible_ip} ansible_user={username} rke2_type=agent node_role=worker")

        inventory_lines.append("\n[new_servers]")
        for node in servers:
            inventory_lines.append(node.hostname)

        inventory_lines.append("\n[new_agents]")
        for node in agents:
            inventory_lines.append(node.hostname)

        return "\n".join(inventory_lines)
```

### Variable Renderer

```python
# backend/app/services/variable_renderer.py

from typing import Dict, Any
from app.models import Cluster, Node, NodeRole
import yaml

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
            vars_dict["registry_user"] = cluster.registry_user
            vars_dict["registry_password"] = cluster.registry_password

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
```

---

## 4. Installation Stage Orchestrator

### Stage Orchestrator Service

```python
# backend/app/services/stage_orchestrator.py

from typing import List, Optional
from sqlalchemy.orm import Session
from app.models import Cluster, Node, NodeRole, NodeStatus, Job, JobStatus
from app.services.inventory_renderer import InventoryRenderer
from app.services.variable_renderer import VariableRenderer
from app.services.ansible_runner import AnsibleRunner
from datetime import datetime
import tempfile
import json

class StageOrchestrator:
    """
    Orchestrates RKE2 installation in proper stages
    Enforces ordering: initial_master → joining_masters → workers
    """

    def __init__(self, db: Session):
        self.db = db
        self.inventory_renderer = InventoryRenderer()
        self.variable_renderer = VariableRenderer()

    def install_cluster(self, cluster: Cluster, job: Job) -> bool:
        """
        Execute full cluster installation following RKE2 stages

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate prerequisites
            self._validate_cluster_ready(cluster)

            # Stage 1: Install initial master
            job.output = "Stage 1: Installing initial master node...\n"
            self.db.commit()

            if not self._install_initial_master(cluster, job):
                return False

            cluster.installation_stage = "initial_master_complete"
            self.db.commit()

            # Stage 2: Install joining masters (if any)
            joining_masters = [n for n in cluster.nodes if n.role == NodeRole.MASTER]
            if joining_masters:
                job.output += "\nStage 2: Installing joining master nodes...\n"
                self.db.commit()

                if not self._install_joining_masters(cluster, job, joining_masters):
                    return False

                cluster.installation_stage = "joining_masters_complete"
                self.db.commit()

            # Stage 3: Install workers
            workers = [n for n in cluster.nodes if n.role == NodeRole.WORKER]
            if workers:
                job.output += "\nStage 3: Installing worker nodes...\n"
                self.db.commit()

                if not self._install_workers(cluster, job, workers):
                    return False

                cluster.installation_stage = "workers_complete"
                self.db.commit()

            # Mark complete
            cluster.installation_stage = "completed"
            job.status = JobStatus.SUCCESS
            job.output += "\n✓ Cluster installation completed successfully\n"
            self.db.commit()

            return True

        except Exception as e:
            job.status = JobStatus.FAILED
            job.output += f"\n✗ Installation failed: {str(e)}\n"
            self.db.commit()
            return False

    def _validate_cluster_ready(self, cluster: Cluster):
        """Validate cluster is ready for installation"""
        # Must have exactly one initial master
        initial_masters = [n for n in cluster.nodes if n.role == NodeRole.INITIAL_MASTER]
        if len(initial_masters) != 1:
            raise ValueError(f"Cluster must have exactly 1 initial master, found {len(initial_masters)}")

        # Must have credential
        if not cluster.credential:
            raise ValueError("Cluster must have SSH credential configured")

        # Must have API IP and token
        if not cluster.rke2_api_ip or not cluster.rke2_token:
            raise ValueError("Cluster must have rke2_api_ip and rke2_token configured")

    def _install_initial_master(self, cluster: Cluster, job: Job) -> bool:
        """
        Install the initial master node
        This node bootstraps the cluster and MUST NOT have server: parameter
        """
        initial_master = next(n for n in cluster.nodes if n.role == NodeRole.INITIAL_MASTER)

        # Update node status
        initial_master.status = NodeStatus.INSTALLING
        initial_master.installation_started_at = datetime.utcnow()
        self.db.commit()

        # Generate inventory for initial master only
        inventory_content = self.inventory_renderer.render_for_stage(cluster, "initial_master")

        # Generate variables
        cluster_vars = self.variable_renderer.render_cluster_vars(cluster)

        # Run playbook
        success = self._run_stage_playbook(
            cluster=cluster,
            job=job,
            playbook="install_initial_master.yml",
            inventory_content=inventory_content,
            extra_vars=cluster_vars
        )

        # Update node status
        initial_master.status = NodeStatus.ACTIVE if success else NodeStatus.FAILED
        initial_master.installation_completed_at = datetime.utcnow()
        if not success:
            initial_master.installation_error = "Playbook execution failed"
        self.db.commit()

        return success

    def _install_joining_masters(self, cluster: Cluster, job: Job, nodes: List[Node]) -> bool:
        """
        Install joining master nodes
        These nodes MUST have server: parameter pointing to initial master
        """
        # Update node statuses
        for node in nodes:
            node.status = NodeStatus.INSTALLING
            node.installation_started_at = datetime.utcnow()
        self.db.commit()

        # Generate inventory
        inventory_content = self.inventory_renderer.render_for_stage(cluster, "joining_masters", nodes)

        # Generate variables
        cluster_vars = self.variable_renderer.render_cluster_vars(cluster)

        # Run playbook
        success = self._run_stage_playbook(
            cluster=cluster,
            job=job,
            playbook="install_joining_masters.yml",
            inventory_content=inventory_content,
            extra_vars=cluster_vars
        )

        # Update node statuses
        for node in nodes:
            node.status = NodeStatus.ACTIVE if success else NodeStatus.FAILED
            node.installation_completed_at = datetime.utcnow()
            if not success:
                node.installation_error = "Playbook execution failed"
        self.db.commit()

        return success

    def _install_workers(self, cluster: Cluster, job: Job, nodes: List[Node]) -> bool:
        """
        Install worker nodes
        These nodes run as rke2-agent and join the cluster
        """
        # Update node statuses
        for node in nodes:
            node.status = NodeStatus.INSTALLING
            node.installation_started_at = datetime.utcnow()
        self.db.commit()

        # Generate inventory
        inventory_content = self.inventory_renderer.render_for_stage(cluster, "workers", nodes)

        # Generate variables
        cluster_vars = self.variable_renderer.render_cluster_vars(cluster)

        # Run playbook
        success = self._run_stage_playbook(
            cluster=cluster,
            job=job,
            playbook="install_workers.yml",
            inventory_content=inventory_content,
            extra_vars=cluster_vars
        )

        # Update node statuses
        for node in nodes:
            node.status = NodeStatus.ACTIVE if success else NodeStatus.FAILED
            node.installation_completed_at = datetime.utcnow()
            if not success:
                node.installation_error = "Playbook execution failed"
        self.db.commit()

        return success

    def _run_stage_playbook(
        self,
        cluster: Cluster,
        job: Job,
        playbook: str,
        inventory_content: str,
        extra_vars: dict
    ) -> bool:
        """
        Execute stage-specific playbook with ephemeral inventory
        """
        # Write inventory to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ini', dir='/tmp/ansible') as inv_file:
            inv_file.write(inventory_content)
            inv_path = inv_file.name

        # Write extra vars to temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', dir='/tmp/ansible') as vars_file:
            json.dump(extra_vars, vars_file)
            vars_path = vars_file.name

        try:
            # Execute via AnsibleRunner
            runner = AnsibleRunner(db=self.db)
            return runner.execute_playbook(
                cluster=cluster,
                job=job,
                playbook_path=f"/ansible/playbooks/{playbook}",
                inventory_path=inv_path,
                extra_vars_file=vars_path
            )
        finally:
            # Cleanup temp files
            import os
            if os.path.exists(inv_path):
                os.remove(inv_path)
            if os.path.exists(vars_path):
                os.remove(vars_path)
```

---

## 5. Stage-Specific Ansible Playbooks

### install_initial_master.yml

```yaml
---
# Install the initial RKE2 master node
# This node bootstraps the cluster and MUST NOT have server: parameter in config.yaml

- hosts: initial_master
  gather_facts: false
  become: yes
  tasks:
  - name: Validate this is the initial master
    assert:
      that:
        - node_role == "initial_master"
      fail_msg: "This playbook is only for initial master nodes"

  - name: Create RKE2 config directory
    file:
      path: /etc/rancher/rke2
      state: directory
      mode: '0755'

  - name: Render config.yaml for initial master
    template:
      src: /ansible/templates/config_initial_master.yaml.j2
      dest: /etc/rancher/rke2/config.yaml
      mode: '0600'

  - name: Render registries.yaml
    template:
      src: /ansible/templates/registries.yaml.j2
      dest: /etc/rancher/rke2/registries.yaml
      mode: '0600'
    when: custom_mirror == 'active'

  - name: Install RKE2 server
    shell: curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION={{ rke2_version }} sh -
    args:
      creates: /usr/local/bin/rke2

  - name: Enable rke2-server service
    systemd:
      name: rke2-server.service
      enabled: yes

  - name: Start rke2-server service
    systemd:
      name: rke2-server.service
      state: started

  - name: Wait for rke2-server to be ready
    wait_for:
      path: /var/lib/rancher/rke2/server/node-token
      timeout: 300

  - name: Wait for Kubernetes API to be ready
    wait_for:
      host: "{{ rke2_api_ip }}"
      port: 6443
      timeout: 300

  - name: Verify initial master is healthy
    shell: /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get nodes
    register: nodes_output
    retries: 10
    delay: 10
    until: nodes_output.rc == 0

  - name: Fetch kubeconfig
    fetch:
      src: /etc/rancher/rke2/rke2.yaml
      dest: /tmp/ansible/kubeconfig_{{ inventory_hostname }}.yaml
      flat: yes
```

### install_joining_masters.yml

```yaml
---
# Install joining master nodes
# These nodes MUST have server: parameter in config.yaml

- hosts: joining_masters
  gather_facts: false
  become: yes
  tasks:
  - name: Validate these are joining masters
    assert:
      that:
        - node_role == "joining_master"
        - rke2_api_ip is defined
        - rke2_token is defined
      fail_msg: "This playbook requires joining_master role and cluster join parameters"

  - name: Create RKE2 config directory
    file:
      path: /etc/rancher/rke2
      state: directory
      mode: '0755'

  - name: Render config.yaml for joining master
    template:
      src: /ansible/templates/config_joining_master.yaml.j2
      dest: /etc/rancher/rke2/config.yaml
      mode: '0600'

  - name: Render registries.yaml
    template:
      src: /ansible/templates/registries.yaml.j2
      dest: /etc/rancher/rke2/registries.yaml
      mode: '0600'
    when: custom_mirror == 'active'

  - name: Install RKE2 server
    shell: curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION={{ rke2_version }} sh -
    args:
      creates: /usr/local/bin/rke2

  - name: Enable rke2-server service
    systemd:
      name: rke2-server.service
      enabled: yes

  - name: Start rke2-server service
    systemd:
      name: rke2-server.service
      state: started

  - name: Wait for rke2-server to join cluster
    wait_for:
      path: /var/lib/rancher/rke2/server/node-token
      timeout: 300

  - name: Verify node joined cluster
    shell: /var/lib/rancher/rke2/bin/kubectl --kubeconfig /etc/rancher/rke2/rke2.yaml get nodes {{ inventory_hostname }}
    register: node_check
    retries: 10
    delay: 10
    until: node_check.rc == 0
```

### install_workers.yml

```yaml
---
# Install worker nodes (rke2-agent)

- hosts: workers
  gather_facts: false
  become: yes
  tasks:
  - name: Validate these are worker nodes
    assert:
      that:
        - node_role == "worker"
        - rke2_api_ip is defined
        - rke2_token is defined
      fail_msg: "This playbook requires worker role and cluster join parameters"

  - name: Create RKE2 config directory
    file:
      path: /etc/rancher/rke2
      state: directory
      mode: '0755'

  - name: Render config.yaml for worker
    template:
      src: /ansible/templates/config_worker.yaml.j2
      dest: /etc/rancher/rke2/config.yaml
      mode: '0600'

  - name: Render registries.yaml
    template:
      src: /ansible/templates/registries.yaml.j2
      dest: /etc/rancher/rke2/registries.yaml
      mode: '0600'
    when: custom_mirror == 'active'

  - name: Install RKE2 agent
    shell: curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION={{ rke2_version }} INSTALL_RKE2_TYPE="agent" sh -
    args:
      creates: /usr/local/bin/rke2

  - name: Enable rke2-agent service
    systemd:
      name: rke2-agent.service
      enabled: yes

  - name: Start rke2-agent service
    systemd:
      name: rke2-agent.service
      state: started

  - name: Wait for agent to be ready
    wait_for:
      timeout: 180
    delegate_to: localhost

  - name: Verify agent is running
    shell: systemctl is-active rke2-agent.service
    register: agent_status
    failed_when: agent_status.stdout != "active"
```

### Configuration Templates

**config_initial_master.yaml.j2:**
```yaml
# Initial master config - NO server parameter
token: {{ rke2_token }}
{% if rke2_additional_sans is defined %}
tls-san:
{% for san in rke2_additional_sans %}
  - {{ san }}
{% endfor %}
{% endif %}
cni: {{ cni }}
data-dir: {{ rke2_data_dir }}
```

**config_joining_master.yaml.j2:**
```yaml
# Joining master config - MUST have server parameter
server: https://{{ rke2_api_ip }}:9345
token: {{ rke2_token }}
{% if rke2_additional_sans is defined %}
tls-san:
{% for san in rke2_additional_sans %}
  - {{ san }}
{% endfor %}
{% endif %}
cni: {{ cni }}
data-dir: {{ rke2_data_dir }}
```

**config_worker.yaml.j2:**
```yaml
# Worker config
server: https://{{ rke2_api_ip }}:9345
token: {{ rke2_token }}
data-dir: {{ rke2_data_dir }}
```

---

## 6. Scale Operations with Hybrid Model

### Adding Nodes to Existing Cluster

```python
# backend/app/services/scale_service.py

class ScaleService:
    """
    Handle cluster scaling operations using hybrid inventory
    """

    def add_nodes(self, cluster: Cluster, new_nodes: List[Node], job: Job) -> bool:
        """
        Add nodes to existing cluster
        All new nodes are treated as "joining" nodes
        """
        # Validate cluster is ready
        if cluster.installation_stage != "completed":
            raise ValueError("Cannot scale cluster that is not fully installed")

        # Determine node roles
        for node in new_nodes:
            # If adding server nodes, they are always "joining" (not initial)
            if node.role == NodeRole.INITIAL_MASTER:
                node.role = NodeRole.MASTER  # Convert to joining master

        # Add to database
        for node in new_nodes:
            node.cluster_id = cluster.id
            node.status = NodeStatus.PENDING
            self.db.add(node)
        self.db.commit()

        # Separate servers and agents
        new_servers = [n for n in new_nodes if n.role == NodeRole.MASTER]
        new_agents = [n for n in new_nodes if n.role == NodeRole.WORKER]

        # Install servers first (if any)
        if new_servers:
            if not self._add_servers(cluster, new_servers, job):
                return False

        # Then install agents
        if new_agents:
            if not self._add_agents(cluster, new_agents, job):
                return False

        return True

    def _add_servers(self, cluster: Cluster, nodes: List[Node], job: Job) -> bool:
        """Add server nodes to existing cluster"""
        # Use joining_masters playbook
        inventory = InventoryRenderer.render_for_scale_add(cluster, nodes)
        vars = VariableRenderer.render_cluster_vars(cluster)

        # Run install_joining_masters.yml
        return self._run_playbook(
            cluster, job, "install_joining_masters.yml", inventory, vars
        )

    def _add_agents(self, cluster: Cluster, nodes: List[Node], job: Job) -> bool:
        """Add agent nodes to existing cluster"""
        inventory = InventoryRenderer.render_for_scale_add(cluster, nodes)
        vars = VariableRenderer.render_cluster_vars(cluster)

        # Run install_workers.yml
        return self._run_playbook(
            cluster, job, "install_workers.yml", inventory, vars
        )
```

### Removing Nodes

```python
def remove_nodes(self, cluster: Cluster, nodes: List[Node], job: Job) -> bool:
    """
    Remove nodes from cluster
    Validates etcd quorum safety before removal
    """
    # Validate removal is safe
    self._validate_removal_safe(cluster, nodes)

    # Mark nodes as draining
    for node in nodes:
        node.status = NodeStatus.DRAINING
    self.db.commit()

    # Generate inventory for nodes to remove
    inventory = InventoryRenderer.render_for_stage(cluster, "all", nodes)
    vars = VariableRenderer.render_cluster_vars(cluster)
    vars["nodes_to_remove"] = [n.hostname for n in nodes]

    # Run remove_node.yml
    success = self._run_playbook(
        cluster, job, "remove_node.yml", inventory, vars
    )

    # Mark as removed
    for node in nodes:
        node.status = NodeStatus.REMOVED if success else NodeStatus.FAILED
    self.db.commit()

    return success

def _validate_removal_safe(self, cluster: Cluster, nodes_to_remove: List[Node]):
    """Validate removal doesn't break quorum"""
    all_masters = [n for n in cluster.nodes if n.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER] and n.status == NodeStatus.ACTIVE]
    masters_being_removed = [n for n in nodes_to_remove if n.role in [NodeRole.INITIAL_MASTER, NodeRole.MASTER]]

    remaining_masters = len(all_masters) - len(masters_being_removed)

    # Etcd requires (n/2)+1 for quorum
    if remaining_masters < 1:
        raise ValueError("Cannot remove all master nodes")

    if len(all_masters) > 1 and remaining_masters < 2:
        raise ValueError("Removing these masters would break etcd quorum")
```

---

## 7. Registered Cluster Support

### Discovering Nodes from Kubeconfig

```python
# backend/app/services/cluster_discovery.py

class ClusterDiscovery:
    """
    Discover cluster nodes from kubeconfig for registered clusters
    """

    def discover_nodes(self, cluster: Cluster) -> List[Node]:
        """
        Use kubectl to discover nodes in registered cluster
        Create Node records in database
        """
        if not cluster.kubeconfig:
            raise ValueError("Cluster has no kubeconfig")

        # Get node details via kubectl
        from app.services.cluster_status_service import get_cluster_status
        status = get_cluster_status(cluster)

        discovered_nodes = []
        node_details = status.get("nodes", {}).get("details", [])

        # Determine roles from kubectl output
        for idx, node_data in enumerate(node_details):
            roles_str = node_data.get("roles", "")

            # Determine role
            if "control-plane" in roles_str or "master" in roles_str:
                # First master is initial, rest are joining
                role = NodeRole.INITIAL_MASTER if idx == 0 else NodeRole.MASTER
            else:
                role = NodeRole.WORKER

            node = Node(
                cluster_id=cluster.id,
                hostname=node_data.get("name"),
                internal_ip=node_data.get("internal_ip"),
                external_ip=node_data.get("external_ip"),
                role=role,
                status=NodeStatus.ACTIVE  # Already running
            )

            self.db.add(node)
            discovered_nodes.append(node)

        self.db.commit()
        return discovered_nodes
```

### Using Discovered Nodes for Scale

Once nodes are discovered and stored in database:
- Scale operations work identically for NEW and REGISTERED clusters
- Both use database as source of truth
- Both use dynamic inventory rendering
- Registered clusters can add/remove nodes just like new clusters

---

## 8. Implementation Checklist

### Phase 1: Database Migration
- [ ] Create Node model
- [ ] Create Alembic migration
- [ ] Migrate existing cluster.nodes JSON to Node records
- [ ] Test migration on development database

### Phase 2: Core Services
- [ ] Implement InventoryRenderer service
- [ ] Implement VariableRenderer service
- [ ] Implement StageOrchestrator service
- [ ] Implement ScaleService refactoring
- [ ] Implement ClusterDiscovery service

### Phase 3: Ansible Playbooks
- [ ] Create install_initial_master.yml
- [ ] Create install_joining_masters.yml
- [ ] Create install_workers.yml
- [ ] Create config templates (initial, joining, worker)
- [ ] Update add_node.yml to use new inventory
- [ ] Update remove_node.yml to use new inventory

### Phase 4: API Updates
- [ ] Update cluster creation endpoint to use Node model
- [ ] Update scale/add endpoint to use new services
- [ ] Update scale/remove endpoint to use new services
- [ ] Update cluster detail endpoint to return nodes from DB
- [ ] Add node discovery endpoint for registered clusters

### Phase 5: Testing
- [ ] Test new cluster creation with staged installation
- [ ] Test scale up (add nodes)
- [ ] Test scale down (remove nodes)
- [ ] Test registered cluster discovery
- [ ] Test scale operations on registered cluster
- [ ] Test migration of existing clusters

### Phase 6: Cleanup
- [ ] Remove old ansible_generator.py static inventory code
- [ ] Remove update_cluster_inventory() workaround
- [ ] Clean up old playbook files
- [ ] Update documentation

---

## 9. Benefits Summary

**Correctness:**
- ✅ Proper RKE2 installation stage ordering enforced
- ✅ Initial master vs joining master distinction
- ✅ Workers only install after control plane is ready

**Reliability:**
- ✅ Database as single source of truth
- ✅ No mutable JSON tracking issues
- ✅ Transactional node state updates

**Flexibility:**
- ✅ Works for both new and registered clusters
- ✅ Dynamic inventory generation
- ✅ Node-specific and cluster-specific variables

**Safety:**
- ✅ Quorum validation before removals
- ✅ Installation state tracking
- ✅ Fail-fast on prerequisite violations

**Maintainability:**
- ✅ Clean separation of concerns
- ✅ Testable components
- ✅ No static file dependencies
