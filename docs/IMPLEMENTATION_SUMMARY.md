# Hybrid Inventory Implementation Summary

## What Was Delivered

### 1. Comprehensive Design Document
**File:** `docs/HYBRID_INVENTORY_DESIGN.md`

A complete architectural blueprint covering:
- Database schema with `Node` model
- Dynamic inventory rendering system
- Stage-aware installation orchestrator
- Stage-specific Ansible playbooks
- Scale operations refactoring
- Registered cluster discovery

### 2. Database Migration
**File:** `backend/migrations/001_add_nodes_table.py`

Runnable migration script that:
- Creates `nodes` table with proper constraints
- Migrates existing `cluster.nodes` JSON to `Node` records
- Preserves role information (initial_master vs master vs worker)
- Adds `installation_stage` and `cluster_vars` columns to clusters
- Removes deprecated `nodes` JSON column
- Includes rollback capability

## Critical Architecture Changes

### Before (Current State)
```
Clusters Table
├─ nodes: JSON [{hostname, ip, role}]  ← Unreliable, mutable tracking issues
└─ Static inventory.ini files          ← Out of sync, hard to maintain

Playbooks
└─ install_rke2.yml                     ← No stage ordering, treats all masters equally
```

### After (Hybrid Model)
```
Database (Source of Truth)
├─ Clusters Table
│  ├─ installation_stage
│  └─ cluster_vars (JSON)
└─ Nodes Table
   ├─ role: initial_master | master | worker
   ├─ status: pending | installing | active | failed | removed
   ├─ internal_ip, external_ip
   └─ node_vars (JSON)

Runtime Services
├─ InventoryRenderer → generates ephemeral inventory from DB
├─ VariableRenderer  → generates Ansible vars from DB
└─ StageOrchestrator → enforces installation order

Stage-Specific Playbooks
├─ install_initial_master.yml    (no server: param)
├─ install_joining_masters.yml   (with server: param)
└─ install_workers.yml           (agent installation)
```

## Key Design Principles

### 1. RKE2 Installation Stages (MANDATORY ORDER)

**Stage 1 - Initial Master:**
- Exactly ONE node
- Installed as `rke2-server`
- Config MUST NOT have `server:` parameter
- Bootstraps the cluster

**Stage 2 - Joining Masters:**
- Additional server nodes
- Installed as `rke2-server`
- Config MUST have `server: https://<initial-master>:9345`

**Stage 3 - Workers:**
- Worker nodes
- Installed as `rke2-agent`
- Config MUST have `server: https://<any-master>:9345`

### 2. Database as Source of Truth

**All cluster topology stored in database:**
- Nodes are first-class entities, not JSON blobs
- Real-time status tracking (pending → installing → active)
- Node-specific and cluster-specific variables
- Proper foreign key relationships and constraints

### 3. Dynamic Inventory Generation

**No static inventory files:**
- Inventory rendered at runtime from database
- Stage-specific inventory generation
- Ephemeral temp files, cleaned up after execution
- Works for both new and registered clusters

### 4. Hybrid Model Benefits

**For New Clusters:**
- Proper stage ordering enforced
- Installation state tracked per-node
- Scale operations use same DB source

**For Registered Clusters:**
- Discover nodes via kubectl
- Store in database
- Scale operations work identically

## Implementation Roadmap

### Phase 1: Database (Week 1)
```bash
# Run migration
cd backend
python migrations/001_add_nodes_table.py upgrade
```

**Deliverables:**
- `nodes` table created
- Existing data migrated
- Old `nodes` JSON column removed

### Phase 2: Core Services (Week 1-2)
**Files to create:**
- `backend/app/services/inventory_renderer.py`
- `backend/app/services/variable_renderer.py`
- `backend/app/services/stage_orchestrator.py`
- `backend/app/services/scale_service.py`
- `backend/app/services/cluster_discovery.py`

**Update:**
- `backend/app/models.py` - Add Node model, update Cluster model

### Phase 3: Ansible Playbooks (Week 2)
**Files to create:**
- `ansible/playbooks/install_initial_master.yml`
- `ansible/playbooks/install_joining_masters.yml`
- `ansible/playbooks/install_workers.yml`
- `ansible/templates/config_initial_master.yaml.j2`
- `ansible/templates/config_joining_master.yaml.j2`
- `ansible/templates/config_worker.yaml.j2`

**Update:**
- `ansible/playbooks/add_node.yml` - Use dynamic inventory
- `ansible/playbooks/remove_node.yml` - Use dynamic inventory

### Phase 4: API Layer (Week 2-3)
**Files to update:**
- `backend/app/routers/clusters.py`
  - POST `/clusters` - Create nodes as Node records
  - POST `/clusters/{id}/scale/add` - Use ScaleService
  - POST `/clusters/{id}/scale/remove` - Use ScaleService
  - GET `/clusters/{id}/scale` - Query nodes from database
  - POST `/clusters/{id}/discover` - Discover registered cluster nodes

- `backend/app/services/cluster_service.py`
  - Use Node model instead of JSON
  - Call StageOrchestrator for installation

- `backend/app/services/ansible_service.py`
  - Remove static inventory generation
  - Use InventoryRenderer

### Phase 5: Testing (Week 3)
**Test scenarios:**
1. Create new 3-node cluster (1 master, 2 workers)
2. Verify stage ordering in logs
3. Scale up: add 2 masters, 3 workers
4. Scale down: remove 1 worker
5. Register existing cluster
6. Discover nodes from registered cluster
7. Scale registered cluster

### Phase 6: Cleanup (Week 3-4)
**Files to remove:**
- `backend/app/services/ansible_generator.py`
- Old static inventory generation code
- `update_cluster_inventory()` workaround

**Documentation:**
- Update README with new architecture
- API documentation updates
- Operator guide for migrations

## Quick Start (Development)

### 1. Run Migration
```bash
cd backend
python migrations/001_add_nodes_table.py upgrade
```

### 2. Review Design
Read `docs/HYBRID_INVENTORY_DESIGN.md` sections:
- Section 2: Database Schema
- Section 3: Inventory Renderer
- Section 4: Stage Orchestrator
- Section 5: Stage-Specific Playbooks

### 3. Implementation Order
1. Add Node model to `models.py`
2. Implement InventoryRenderer
3. Implement VariableRenderer
4. Create stage-specific playbooks
5. Implement StageOrchestrator
6. Update cluster creation to use orchestrator
7. Refactor scale operations

## Safety Features

### Quorum Protection
```python
def _validate_removal_safe(cluster, nodes_to_remove):
    """Prevent removing masters that would break etcd quorum"""
    remaining_masters = count_masters - len(masters_being_removed)
    if remaining_masters < 1:
        raise ValueError("Cannot remove all master nodes")
```

### Stage Validation
```python
def _validate_cluster_ready(cluster):
    """Ensure cluster configuration is valid before installation"""
    if len(initial_masters) != 1:
        raise ValueError("Must have exactly 1 initial master")
    if not cluster.rke2_token:
        raise ValueError("Must have join token")
```

### Node State Tracking
```python
# Installation lifecycle
PENDING → INSTALLING → ACTIVE
          ↓
       FAILED

# Removal lifecycle
ACTIVE → DRAINING → REMOVED
         ↓
      FAILED
```

## Breaking Changes

### API Changes
**Before:**
```json
{
  "nodes": [
    {"hostname": "node1", "ip": "10.0.0.1", "role": "server"}
  ]
}
```

**After:**
```json
{
  "nodes": [
    {
      "hostname": "node1",
      "internal_ip": "10.0.0.1",
      "external_ip": null,
      "role": "initial_master",
      "use_external_ip": false
    }
  ]
}
```

### Database Schema
- `clusters.nodes` JSON column → `nodes` table
- New enums: `NodeRole`, `NodeStatus`
- New columns: `clusters.installation_stage`, `clusters.cluster_vars`

### Ansible Variables
- New host vars: `node_role` (initial_master | joining_master | worker)
- Changed: `rke2_type` still exists (server | agent) for compatibility
- Templates must distinguish initial vs joining masters

## Rollback Plan

If migration causes issues:

```bash
# Rollback database
cd backend
python migrations/001_add_nodes_table.py downgrade

# Revert code changes
git revert <commit-hash>

# Restart services
docker-compose restart
```

The migration includes a `downgrade()` function that:
- Converts `Node` records back to `clusters.nodes` JSON
- Drops `nodes` table
- Removes added columns
- Restores original schema

## Success Criteria

✅ **Correctness:**
- Installation follows proper stages (initial → joining → workers)
- Initial master config has NO `server:` parameter
- Joining masters/workers have correct `server:` parameter

✅ **Reliability:**
- Database is single source of truth
- No race conditions or stale data
- Node status accurately reflects reality

✅ **Compatibility:**
- New clusters install correctly
- Registered clusters work identically
- Scale operations work for both types

✅ **Safety:**
- Cannot remove all masters
- Cannot break etcd quorum
- Fail-fast on invalid configuration

## Next Steps

1. **Review the design document** (`HYBRID_INVENTORY_DESIGN.md`)
2. **Run the migration** in a development environment
3. **Begin Phase 2** implementation (Core Services)
4. **Create test clusters** to validate behavior
5. **Iterate based on findings**

## Questions & Support

**Design Questions:**
- Refer to `HYBRID_INVENTORY_DESIGN.md` sections
- Check code examples in design doc

**Migration Issues:**
- Migration is reversible via `downgrade()`
- Test on development database first
- Backup production database before running

**Implementation Help:**
- Design doc includes complete code examples
- Services are independently testable
- Start with InventoryRenderer (simplest component)
