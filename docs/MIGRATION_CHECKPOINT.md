# Migration Checkpoint - Hybrid Inventory Phase 1

**Date:** 2025-12-29
**Status:** Database migrated, basic services created, system restarted

## What Was Completed

### 1. Database Migration ✅
- **Migration file:** `backend/migrations/001_add_nodes_table.py`
- **Status:** Successfully executed
- **Results:**
  - Created `nodes` table with all fields
  - Migrated 13 nodes from 4 clusters
  - Added `installation_stage` column to clusters
  - Added `cluster_vars` column to clusters
  - Removed old `nodes` JSON column from clusters

**Migration command:**
```bash
docker exec rke2-automation-backend-1 python migrations/001_add_nodes_table.py upgrade
```

**Rollback command (if needed):**
```bash
docker exec rke2-automation-backend-1 python migrations/001_add_nodes_table.py downgrade
```

### 2. Model Updates ✅
**File:** `backend/app/models.py`

**Added:**
- `NodeRole` enum (initial_master, master, worker)
- `NodeStatus` enum (pending, installing, active, failed, draining, removed)
- `Node` model with:
  - cluster_id (FK to clusters)
  - hostname, internal_ip, external_ip
  - role, status
  - use_external_ip (boolean)
  - node_vars (JSON)
  - installation tracking fields
  - ansible_ip property

**Updated Cluster model:**
- Removed: `nodes = Column(JSON)`
- Added: `cluster_nodes` relationship to Node
- Added: `installation_stage` column
- Added: `cluster_vars` column

### 3. Services Created ✅

**InventoryRenderer** - `backend/app/services/inventory_renderer.py`
- `render_for_stage(cluster, stage, nodes)` - Stage-specific inventory
- `render_for_scale_add(cluster, new_nodes)` - Scale operations
- Supports: initial_master, joining_masters, workers, all

**VariableRenderer** - `backend/app/services/variable_renderer.py`
- `render_cluster_vars(cluster)` - Cluster-wide Ansible vars
- `render_node_vars(node)` - Node-specific vars

### 4. Config Templates Created ✅

**ansible/templates/**
- `config_initial_master.yaml.j2` - NO server parameter (bootstraps cluster)
- `config_joining_master.yaml.j2` - WITH server parameter (joins cluster)
- `config_worker.yaml.j2` - Agent configuration

## Current System State

### Database Schema
```
clusters table:
  - (removed) nodes: JSON
  - (new) installation_stage: VARCHAR
  - (new) cluster_vars: JSON

nodes table (NEW):
  - id, cluster_id
  - hostname, internal_ip, external_ip
  - role (enum), status (enum)
  - use_external_ip
  - node_vars (JSON)
  - installation tracking fields
  - Constraint: UNIQUE(cluster_id, hostname)
```

### Existing Data
- 4 clusters in database
- 13 nodes migrated successfully
- All nodes marked as 'active' status
- First server node of each cluster = 'initial_master'
- Other server nodes = 'master'
- Agent nodes = 'worker'

## What Still Uses Old Approach

The following files STILL use the old static inventory approach and need updating:

### ⚠️ Not Yet Updated:

1. **backend/app/services/cluster_service.py**
   - `create_new_cluster()` - Still tries to create with nodes JSON
   - Needs to: Create Node records instead

2. **backend/app/services/ansible_generator.py**
   - `generate_ansible_artifacts()` - Still expects `cluster.nodes` JSON
   - Needs to: Use `cluster.cluster_nodes` relationship

3. **backend/app/routers/clusters.py**
   - Scale endpoints still work with old approach
   - Needs gradual update

4. **frontend/src/pages/CreateCluster.jsx**
   - Still sends nodes as JSON array
   - May need schema adjustment

## Next Steps (Gradual Migration)

### Phase 1: Make Existing System Work with Node Model
1. ✅ Update `models.py` - Remove `nodes` column
2. ✅ Restart backend
3. ⏳ Update `cluster_service.py` - Create Node records
4. ⏳ Update `ansible_generator.py` - Use cluster.cluster_nodes
5. ⏳ Test cluster creation
6. ⏳ Test existing cluster viewing

### Phase 2: Update Scale Operations
1. Update scale/add endpoint to create Node records
2. Update scale/remove to update Node status
3. Use InventoryRenderer for scale operations
4. Test scale up/down

### Phase 3: Stage-Based Installation (Future)
1. Implement StageOrchestrator service
2. Create stage-specific playbooks
3. Update install endpoint to use staged approach
4. Gradually migrate to proper RKE2 installation ordering

## Rollback Instructions

If anything breaks:

```bash
# 1. Rollback database
docker exec rke2-automation-backend-1 python migrations/001_add_nodes_table.py downgrade

# 2. Restore old models.py
git checkout HEAD -- backend/app/models.py

# 3. Restart backend
docker-compose restart backend
```

## Files Changed Summary

### Modified:
- `backend/app/models.py` - Node model added, Cluster updated
- `backend/migrations/001_add_nodes_table.py` - Created
- `backend/app/services/inventory_renderer.py` - Created
- `backend/app/services/variable_renderer.py` - Created
- `ansible/templates/config_initial_master.yaml.j2` - Created
- `ansible/templates/config_joining_master.yaml.j2` - Created
- `ansible/templates/config_worker.yaml.j2` - Created

### Documentation:
- `docs/HYBRID_INVENTORY_DESIGN.md` - Full design
- `docs/IMPLEMENTATION_SUMMARY.md` - Implementation plan
- `docs/MIGRATION_CHECKPOINT.md` - This file

## Testing Status

- ❌ New cluster creation - Not tested yet (needs service updates)
- ❌ Existing cluster viewing - Not tested yet
- ❌ Scale operations - Not tested yet
- ✅ Database migration - Tested and working
- ✅ Backend startup - Working after model fix

## Known Issues

1. **Cluster creation will fail** - `cluster_service.py` still tries to use nodes JSON
2. **Ansible generation will fail** - `ansible_generator.py` expects old format
3. **Frontend unchanged** - Still sends old node format

## Important Notes

- Database has been migrated - **DO NOT run migration again** unless you rollback first
- Old `nodes` column is gone from database
- All existing node data is now in `nodes` table
- Backend restart was necessary after model changes
- System is in **transitional state** - not fully functional until services are updated

## Quick Recovery

If you just need to get the system working again with old approach:

```bash
# Rollback everything
docker exec rke2-automation-backend-1 python migrations/001_add_nodes_table.py downgrade
git stash  # Save new files
git checkout HEAD -- backend/app/models.py
docker-compose restart backend
```

Then the old system will work again with JSON nodes column.
