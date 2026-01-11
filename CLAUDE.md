# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RKE2 Automation is an internal lifecycle management tool for deploying and operating RKE2 (Rancher Kubernetes Engine 2) clusters on-premise. It provides a centralized Web UI and REST API to automate cluster installation, scaling, and monitoring while enforcing operational safety through guardrails.

**Stack:** FastAPI (Python) + React (Vite) + Ansible + SQLite + AWS Bedrock (LLM)

## Development Commands

### Environment Setup
```bash
# Generate encryption key for credentials
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Copy and configure environment
cp .env.example .env
# Add AWS credentials and ENCRYPTION_KEY to .env
```

### Running the Application
```bash
# Start all services (backend, frontend, ansible-runner)
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Stop services
docker-compose down
```

**Access Points:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Backend Development
```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Run backend directly (without Docker)
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run database migrations
cd backend/migrations
python 001_initial_schema.py
python 002_add_jobs_table.py
python 003_add_cluster_lock_fields.py
```

### Frontend Development
```bash
# Install dependencies
cd frontend
npm install

# Run dev server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Security Scanning
```bash
# Scan for secrets before committing
./scripts/scan-secrets.sh
```

## Architecture

### Database as Source of Truth
The database (`data/rke2.db`) is the primary source of truth, NOT static Ansible inventory files. Inventories are dynamically generated into ephemeral files (`ansible/clusters/<cluster-name>/`) before each Ansible run.

**Key Models:**
- `Cluster` - Cluster definitions with lock fields for concurrency control
- `Node` - Individual nodes (masters/workers) with status tracking
- `Job` - Async operation tracking (install, scale, remove)
- `Credential` - Encrypted SSH keys and access credentials

### Service Layer Pattern
Business logic MUST reside in `backend/app/services/`, NOT in routers. Routers only handle HTTP concerns.

**Critical Services:**
- `ansible_service.py` - Executes Ansible playbooks via ansible-runner, manages job lifecycle
- `cluster_lock_service.py` - Prevents concurrent operations on same cluster (acquire/release lock)
- `inventory_renderer.py` - Generates dynamic Ansible inventory from database
- `variable_renderer.py` - Renders Ansible extra_vars from cluster/node data
- `cluster_status_service.py` - Queries Kubernetes API for real-time cluster/node status
- `node_sync_service.py` - Syncs database node status with actual Kubernetes state
- `llm_service.py` / `bedrock_deepseek.py` - AWS Bedrock integration for log analysis
- `encryption_service.py` - Fernet-based encryption for SSH credentials

### Stage-Aware RKE2 Installation
RKE2 bootstrap requires strict ordering to prevent race conditions:

1. **initial_master** - First server node bootstraps etcd
2. **joining_masters** - Additional servers join existing etcd cluster
3. **workers** - Agent nodes join after control plane is stable

The `StageOrchestrator` (in `ansible_service.py`) enforces this sequence. Database field `node.stage` tracks each node's installation phase.

### Cluster Lock & Guardrails
Prevents destructive operations and concurrent modifications:

**Cluster Lock:**
- Uses `SELECT FOR UPDATE` to prevent race conditions
- Returns HTTP 409 if cluster is busy with another operation
- Automatically released in finally blocks even on failure
- Fields: `operation_status`, `current_job_id`, `operation_locked_by`

**Guardrails:**
- **G1 (Bootstrap Prerequisite):** Initial master must be ACTIVE before adding nodes
- **G2 (Safe Master Removal):** Prevents removing last master or breaking etcd quorum
- **G3 (Split Master+Worker):** Sequences master and worker additions separately
- **G4 (Node Identity):** Prevents duplicate hostname/IP entries

### Real-Time Job Logs
Uses Server-Sent Events (SSE) via `sse-starlette` to stream Ansible playbook output to the frontend. Provides live terminal experience without WebSocket complexity.

**Endpoint:** `GET /api/jobs/{job_id}/stream`

### Credential Isolation
SSH credentials are managed separately from cluster definitions, allowing:
- One credential set reused across multiple clusters
- Global credential rotation without touching cluster configs
- Encrypted storage using Fernet symmetric encryption

## Key Playbooks

Located in `ansible/playbooks/`:
- `install_rke2.yml` - Initial cluster installation with stage awareness
- `add_node.yml` - Scale up by adding masters or workers
- `remove_node.yml` - Scale down by removing nodes (with drain/cordon)
- `uninstall_rke2.yml` - Complete cluster teardown
- `pre_upgrade_check.yml` - Readiness assessment before upgrades
- `check_access.yml` - Validate SSH connectivity and sudo permissions

## Coding Standards

### Backend (Python/FastAPI)
- **Strict Typing:** Always use type hints for function arguments and return values
- **Pydantic Models:** Use Pydantic schemas for all request/response models, never return SQLAlchemy models directly
- **Service Pattern:** Business logic in `app/services/`, routers only handle HTTP
- **Async First:** Use `async def` for handlers/services unless blocking I/O (ansible-runner runs in threads)
- **Error Handling:** Use `HTTPException` for API errors, return consistent JSON responses
- **Logging:** Use standard `logging` module, avoid `print()` statements

### Frontend (React/Vite)
- **Functional Components:** Use Hooks exclusively, no Class components
- **No Heavy Frameworks:** Do NOT add Tailwind/Bootstrap/Material UI - use vanilla CSS in `index.css`
- **API Calls:** Use centralized `src/api.js` client, never `fetch` directly in components
- **Component Size:** Keep under 300 lines, break large UIs into `src/components/`

### Ansible & DevOps
- **Idempotency:** All playbooks MUST be idempotent (re-running should be safe)
- **Variable Usage:** Use `VariableRenderer` service to pass data from Python to Ansible
- **Security:** Never hardcode secrets, use environment variables or `EncryptionService`

## Common Workflows

### Creating a New Cluster
1. User fills form (name, RKE2 version, CNI plugin)
2. Backend creates Cluster and initial master Node records
3. Backend generates Ansible artifacts in `ansible/clusters/<name>/`
4. User triggers install job
5. Ansible playbook runs in `initial_master` stage
6. Backend polls node status and updates database

### Scaling Up (Adding Nodes)
1. Cluster lock acquired via `cluster_lock_service.acquire_cluster_lock()`
2. G1 guardrail checks initial master is ACTIVE
3. If adding both masters+workers, G3 sequences them separately
4. G4 validates no duplicate hostname/IP
5. Job created with operation type (scale_add_masters/workers)
6. Ansible playbook runs in appropriate stage (joining_masters/workers)
7. Lock released in finally block

### Scaling Down (Removing Nodes)
1. Cluster lock acquired
2. G2 guardrail validates safe master removal (quorum, last master check)
3. Requires `confirm_master_removal=true` query param for masters
4. Job created with operation type (scale_remove)
5. Ansible drains/cordons node, then uninstalls RKE2
6. Node deleted from database
7. Lock released

### Node Status Sync
Database node status may drift from actual Kubernetes state. Use:
- **Manual:** "Sync Nodes" button in cluster detail UI
- **Automatic:** Status refresh in UI triggers backend sync
- **Backend Service:** `node_sync_service.sync_nodes_for_cluster(cluster_id)`

## Important Notes

- **Ansible artifacts** in `ansible/clusters/` are gitignored (contain sensitive SSH keys)
- **Database file** `data/rke2.db` is gitignored (contains encrypted credentials)
- **Container execution:** Backend uses `docker exec` to run Ansible inside `ansible-runner` container
- **Lock timeout:** Currently no automatic timeout for stuck locks (manual intervention required)
- **Port 9345:** RKE2 API port used for bootstrap health checks (may fail due to firewalls)

## Troubleshooting

**409 Conflict Error:**
Another operation is running on the cluster. Check `GET /api/jobs?cluster_id=X` for running jobs. Wait for completion or manually release lock if stuck.

**Node Status PENDING but Kubernetes is Running:**
Database is out of sync. Use "Sync Nodes" button or call `POST /api/clusters/{id}/sync-nodes`.

**Ansible Job Fails with SSH Error:**
Verify credentials in database are correct and nodes are reachable on port 22. Check `GET /api/credentials` and test with `check_access.yml` playbook.

**Migration Issues:**
Run migrations in order from `backend/migrations/`. Each script is standalone and can be re-run safely.
