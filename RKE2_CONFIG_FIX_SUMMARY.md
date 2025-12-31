# RKE2 Configuration Fix Summary

## Problem
The old `config.yaml.j2` used conditional logic based on `rke2_type` to add the `server:` parameter:
```yaml
{% if rke2_type != "server" %}
server: https://{{ rke2_api_ip }}:9345
{% endif %}
```

**This was WRONG because:**
- ALL masters (initial + joining) had `rke2_type: server`
- This meant NO masters got the `server:` parameter
- Joining masters MUST have `server:` to join the cluster
- Only the initial master should NOT have `server:`

## Solution
Implemented role-based configuration using `NodeRole` from database:

### 1. Backend Changes ([ansible_generator.py](backend/app/services/ansible_generator.py))
- Generate `host_vars/<hostname>.yaml` for each node
- Set `config_template` based on `node.role`:
  - `INITIAL_MASTER` → `config_initial_master.yaml.j2`
  - `MASTER` → `config_joining_master.yaml.j2`
  - `WORKER` → `config_worker.yaml.j2`

### 2. Playbook Changes
- [install_rke2.yml](ansible/playbooks/install_rke2.yml): Use `{{ config_template }}` variable
- [add_node.yml](ansible/playbooks/add_node.yml): Use `{{ config_template }}` variable

### 3. Add Node Flow ([ansible_service.py](backend/app/services/ansible_service.py))
- `execute_add_nodes()` now creates host_vars for new nodes
- Determines role based on existing master count:
  - If `existing_masters > 0`: new servers → `MASTER` (joining)
  - If `existing_masters == 0`: first server → `INITIAL_MASTER`
  - All agents → `WORKER`

## Example Configurations

### HA Cluster (3 Masters + 1 Worker)

#### Initial Master (m1) - ✅ NO server parameter
```yaml
# RKE2 Configuration for Initial Master Node
# This node bootstraps the cluster - MUST NOT have 'server' parameter

token: F9HWlc--H8NXSJGqaxjrFdDl-GmYheqLY8edoQBxWJM
tls-san:
  - 10.0.1.10
  - 10.0.1.11
  - 10.0.1.12
cni: canal
data-dir: /var/lib/rancher/rke2
```

#### Joining Master (m2) - ✅ HAS server parameter
```yaml
# RKE2 Configuration for Joining Master Nodes
# These nodes join an existing cluster - MUST have 'server' parameter

server: https://10.0.1.10:9345
token: F9HWlc--H8NXSJGqaxjrFdDl-GmYheqLY8edoQBxWJM
tls-san:
  - 10.0.1.10
  - 10.0.1.11
  - 10.0.1.12
cni: canal
data-dir: /var/lib/rancher/rke2
```

#### Joining Master (m3) - ✅ HAS server parameter
```yaml
# RKE2 Configuration for Joining Master Nodes
# These nodes join an existing cluster - MUST have 'server' parameter

server: https://10.0.1.10:9345
token: F9HWlc--H8NXSJGqaxjrFdDl-GmYheqLY8edoQBxWJM
tls-san:
  - 10.0.1.10
  - 10.0.1.11
  - 10.0.1.12
cni: canal
data-dir: /var/lib/rancher/rke2
```

#### Worker (w1) - ✅ HAS server parameter
```yaml
# RKE2 Configuration for Worker Nodes (agents)
# These nodes join as workers

server: https://10.0.1.10:9345
token: F9HWlc--H8NXSJGqaxjrFdDl-GmYheqLY8edoQBxWJM
data-dir: /var/lib/rancher/rke2
```

## Files Changed

1. **[backend/app/services/ansible_generator.py](backend/app/services/ansible_generator.py:117-132)**
   - Added host_vars generation with `config_template` mapping

2. **[backend/app/services/ansible_service.py](backend/app/services/ansible_service.py:347-390)**
   - Updated `execute_add_nodes()` to create host_vars for new nodes
   - Added logic to determine INITIAL_MASTER vs MASTER based on existing masters

3. **[ansible/playbooks/install_rke2.yml](ansible/playbooks/install_rke2.yml:18)**
   - Changed from `config.yaml.j2` to `{{ config_template }}`

4. **[ansible/playbooks/add_node.yml](ansible/playbooks/add_node.yml:21)**
   - Changed from `config.yaml.j2` to `{{ config_template }}`

## Templates (Already Existed)

- **[config_initial_master.yaml.j2](ansible/templates/config_initial_master.yaml.j2)** - NO server parameter
- **[config_joining_master.yaml.j2](ansible/templates/config_joining_master.yaml.j2)** - HAS server parameter
- **[config_worker.yaml.j2](ansible/templates/config_worker.yaml.j2)** - HAS server parameter

## Design Principles Met

✅ **Role-based logic** - Configuration determined purely by `NodeRole`, not master count
✅ **Database-driven** - Initial master IP resolved from DB (`rke2_api_ip`)
✅ **Minimal changes** - No redesign of installation stages or state machines
✅ **Idempotent** - Same role always produces same config
✅ **Clear separation** - Three distinct templates for three distinct roles
✅ **Add node support** - Dynamic host_vars creation when scaling cluster

## Testing

Tested with HA cluster (cluster ID 11, name: test-ha):
- 1 INITIAL_MASTER (m1) - config rendered without `server:` ✓
- 2 MASTER nodes (m2, m3) - configs rendered with `server: https://10.0.1.10:9345` ✓
- 1 WORKER (w1) - config rendered with `server: https://10.0.1.10:9345` ✓
