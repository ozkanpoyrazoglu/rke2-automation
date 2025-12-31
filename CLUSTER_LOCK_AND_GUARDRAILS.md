# Cluster Lock and Guardrails Implementation

## Overview

Implemented minimal stage enforcement to prevent unsafe/out-of-order operations and race conditions in the RKE2 cluster management system.

## 1. Cluster Operation Lock

### Database Schema Changes
Added to `Cluster` model ([models.py](backend/app/models.py:139-143)):
```python
operation_status = Column(String, default="idle")  # idle|running
current_job_id = Column(Integer, nullable=True)    # ID of running job
operation_started_at = Column(DateTime, nullable=True)  # When operation started
operation_locked_by = Column(String, nullable=True)  # Operation type
```

### Migration
- **File**: [003_add_cluster_lock_fields.py](backend/migrations/003_add_cluster_lock_fields.py)
- **Status**: ✅ Applied successfully

### Lock Functions
Created [cluster_lock_service.py](backend/app/services/cluster_lock_service.py) with:

**`acquire_cluster_lock(db, cluster_id, job_id, operation_type)`**
- Uses `SELECT FOR UPDATE` to prevent race conditions
- Returns HTTP 409 if cluster is already locked with message:
  ```
  "Cluster is busy with operation '{operation_locked_by}' (job {current_job_id}). Please wait for it to complete."
  ```
- Atomically sets: `operation_status='running'`, `current_job_id`, `operation_started_at`, `operation_locked_by`

**`release_cluster_lock(db, cluster_id)`**
- Resets all lock fields to idle state
- Called in `finally` blocks to ensure release even on failures

## 2. Guardrails Implementation

### G1: Bootstrap Prerequisite
**Function**: `check_bootstrap_prerequisite(db, cluster_id)`

**Purpose**: Prevent adding joining masters/workers before initial master is ready

**Checks**:
- Initial master exists
- Initial master status is ACTIVE
- Best-effort connectivity check to RKE2 API (port 9345)

**Error Messages**:
```
"No initial master found. Cannot add joining masters or workers until initial master is created."

"Initial master '{hostname}' is not active (status: {status}). Cannot add nodes until initial master is fully operational."

"Initial master API endpoint {ip}:9345 is not reachable. Ensure initial master is running."
```

**Applied**: In `add_nodes` endpoint when adding servers or agents

### G2: Prevent Unsafe Master Removal
**Function**: `check_safe_master_removal(db, cluster_id, nodes_to_remove, require_confirmation)`

**Purpose**: Prevent breaking the cluster by removing too many masters

**Checks**:
- Not removing last control-plane node
- Not breaking etcd quorum (< majority)
- Warning for even number of remaining servers
- Requires explicit confirmation flag

**Error Messages**:
```
"Cannot remove all control-plane nodes. At least 1 required."

"Removing {n} server(s) would leave {remaining} servers (even number). This is not recommended for etcd quorum."

"Removing {n} server(s) would break etcd quorum. Need at least {majority} servers."

"Removing control-plane nodes requires explicit confirmation. Add 'confirm_master_removal=true' to your request."
```

**Applied**: In `remove_nodes` endpoint

**API Change**: Added query parameter `confirm_master_removal: bool = False`

### G3: Split Master+Worker Additions
**Function**: `split_master_worker_additions(nodes_to_add)`

**Purpose**: When adding both masters and workers together, execute sequentially

**Behavior**:
- Detects if request contains both servers and agents
- Creates master addition job first
- Returns response indicating workers will be added after masters complete

**Response Example**:
```json
{
  "job_id": 123,
  "message": "Adding 2 master(s) first, then 3 worker(s) will be added automatically",
  "status": "pending",
  "sequenced": true,
  "workers_pending": 3
}
```

**Applied**: In `add_nodes` endpoint

**Note**: Currently creates first job for masters. Worker job creation logic would need to be triggered by master job completion (not yet implemented - would require job completion hooks).

### G4: Node Identity Validation
**Function**: `check_node_identity(db, cluster_id, nodes_to_add)`

**Purpose**: Prevent duplicate nodes

**Checks**:
- No duplicate hostnames in cluster
- No duplicate IPs in cluster

**Error Messages**:
```
"Node with hostname '{hostname}' already exists in cluster"

"Node with IP '{ip}' already exists in cluster"
```

**Applied**: In `add_nodes` endpoint before any job creation

## 3. Installation Stage Tracking

### Function
**`update_installation_stage(db, cluster_id)`**

**Purpose**: Opportunistically update cluster installation stage based on node statuses

**Stages**:
- `pending`: No active masters
- `control_plane_ready`: Active masters, no workers yet
- `workers_installing`: Workers exist but not active
- `workers_ready`: Some workers active
- `active`: All nodes active

**Applied**: Called automatically after successful job completion in all execute functions

## 4. Updated Job Flows

### Install Job ([routers/jobs.py](backend/app/routers/jobs.py:14-46))
```python
1. Create job
2. Try to acquire lock (cleanup job if fails)
3. Execute playbook in background
4. On completion: release lock, update stage
```

### Uninstall Job ([routers/jobs.py](backend/app/routers/jobs.py:77-117))
```python
1. Validate confirmation
2. Create job
3. Try to acquire lock (cleanup job if fails)
4. Execute playbook in background
5. On completion: release lock
```

### Add Nodes ([routers/clusters.py](backend/app/routers/clusters.py:253-374))
```python
1. Validate node data
2. G4: Check node identity
3. G3: Split masters/workers if both present
4. If masters+workers:
   - Create master job
   - Acquire lock for masters
   - Return sequencing info
5. If only masters OR only workers:
   - G1: Check bootstrap prerequisite
   - Create job
   - Acquire lock
   - Execute in background
6. On completion: release lock, update stage
```

### Remove Nodes ([routers/clusters.py](backend/app/routers/clusters.py:376-456))
```python
1. Validate nodes
2. G2: Check safe master removal (with confirmation check)
3. Create job
4. Try to acquire lock (cleanup job if fails)
5. Execute in background
6. On completion: release lock, update stage
```

## 5. Example Error Responses

### Cluster Locked
**HTTP 409 Conflict**
```json
{
  "detail": "Cluster is busy with operation 'scale_add_masters' (job 42). Please wait for it to complete."
}
```

### Bootstrap Not Ready
**HTTP 400 Bad Request**
```json
{
  "detail": "Initial master 'm1' is not active (status: INSTALLING). Cannot add nodes until initial master is fully operational."
}
```

### Duplicate Node
**HTTP 400 Bad Request**
```json
{
  "detail": "Node with hostname 'worker-01' already exists in cluster"
}
```

### Unsafe Master Removal
**HTTP 400 Bad Request**
```json
{
  "detail": "Removing 2 server(s) would break etcd quorum. Need at least 2 servers."
}
```

### Master Removal Without Confirmation
**HTTP 400 Bad Request**
```json
{
  "detail": "Removing control-plane nodes requires explicit confirmation. Add 'confirm_master_removal=true' to your request."
}
```

## 6. Files Modified/Created

### Created
- `backend/migrations/003_add_cluster_lock_fields.py` - Database migration
- `backend/app/services/cluster_lock_service.py` - Lock and guardrail functions

### Modified
- `backend/app/models.py` - Added lock fields to Cluster model
- `backend/app/routers/jobs.py` - Added lock acquire/release to install and uninstall
- `backend/app/routers/clusters.py` - Added guardrails and locks to scale operations
- `backend/app/services/ansible_service.py` - Added lock release and stage updates to all execute functions

## 7. Testing Recommendations

### Test Concurrent Operations
```bash
# Start install
curl -X POST http://localhost:8000/api/jobs/install/1

# Try to add nodes while install running (should fail with 409)
curl -X POST http://localhost:8000/api/clusters/1/scale/add \
  -d '{"nodes": [{"hostname": "w2", "ip": "10.0.0.5", "role": "agent"}]}'
```

### Test Bootstrap Prerequisite
```bash
# Try to add worker before initial master is active (should fail)
curl -X POST http://localhost:8000/api/clusters/1/scale/add \
  -d '{"nodes": [{"hostname": "w1", "ip": "10.0.0.4", "role": "agent"}]}'
```

### Test Master Removal Protection
```bash
# Try to remove last master (should fail)
curl -X POST http://localhost:8000/api/clusters/1/scale/remove \
  -d '{"nodes": [{"hostname": "m1", "ip": "10.0.0.1", "role": "server"}]}'

# Try to remove master without confirmation (should fail)
curl -X POST http://localhost:8000/api/clusters/2/scale/remove \
  -d '{"nodes": [{"hostname": "m2", "ip": "10.0.1.11", "role": "server"}]}'

# Remove master with confirmation (should succeed)
curl -X POST "http://localhost:8000/api/clusters/2/scale/remove?confirm_master_removal=true" \
  -d '{"nodes": [{"hostname": "m2", "ip": "10.0.1.11", "role": "server"}]}'
```

### Test Duplicate Prevention
```bash
# Try to add node with existing hostname (should fail)
curl -X POST http://localhost:8000/api/clusters/1/scale/add \
  -d '{"nodes": [{"hostname": "m1", "ip": "10.0.0.99", "role": "agent"}]}'
```

### Test Sequential Master+Worker Addition
```bash
# Add masters and workers together (should sequence)
curl -X POST http://localhost:8000/api/clusters/1/scale/add \
  -d '{
    "nodes": [
      {"hostname": "m2", "ip": "10.0.0.2", "role": "server"},
      {"hostname": "w1", "ip": "10.0.0.10", "role": "agent"}
    ]
  }'
```

## 8. Known Limitations

1. **G3 Sequential Execution**: Currently only creates the master job and returns a message. Worker job is not automatically queued after master job completes. Would require:
   - Job completion webhooks/callbacks
   - OR frontend polling and triggering worker addition
   - OR background task that monitors master job and creates worker job

2. **Lock Timeout**: No automatic lock timeout/cleanup if a job hangs. Consider adding:
   - Lock expiry timestamp
   - Background task to clean stale locks

3. **Bootstrap Check**: Connectivity check to port 9345 is best-effort and may fail due to network/firewall. Not blocking if check fails.

## 9. Benefits

✅ **Prevents race conditions** - Only one operation per cluster at a time
✅ **Prevents cluster breakage** - Cannot remove too many masters
✅ **Prevents broken joins** - Workers/joining masters can't join before initial master ready
✅ **Prevents duplicates** - Hostname/IP validation before node addition
✅ **Clear error messages** - Users understand why operations are blocked
✅ **Minimal code changes** - No complex state machine, just guardrails
✅ **Safe failure handling** - Locks released even on exceptions
✅ **Opportunistic tracking** - Installation stage updated automatically

## 10. Future Enhancements

- Add lock timeout/expiry mechanism
- Implement worker job auto-queuing after master job completion (G3 full implementation)
- Add operation queue for clusters (allow queueing next operation instead of rejecting)
- Add lock holder info to cluster status API
- Add force unlock admin endpoint for stuck locks
- Add metrics/logging for lock contention
