# RKE2 Automation - Quick Start Guide

## Setup

### 1. Generate Encryption Key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add:
# - ENCRYPTION_KEY=<generated-key>
# - AWS credentials (optional, for LLM summaries)
```

### 3. Start Services

```bash
docker-compose up -d
```

**Services:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Usage Flow

### Step 1: Create SSH Credential

```bash
curl -X POST http://localhost:8000/api/credentials \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-ssh-key",
    "username": "ubuntu",
    "credential_type": "ssh_key",
    "secret": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----"
  }'
```

**Response:**
```json
{
  "id": 1,
  "name": "my-ssh-key",
  "username": "ubuntu",
  "credential_type": "ssh_key",
  "created_at": "2025-12-25T15:54:06.015028"
}
```

### Step 2: Test Access (Optional but Recommended)

```bash
curl -X POST http://localhost:8000/api/credentials/test-access \
  -H "Content-Type: application/json" \
  -d '{
    "credential_id": 1,
    "hosts": [
      {"hostname": "server-1", "ip": "192.168.1.10"},
      {"hostname": "agent-1", "ip": "192.168.1.20"}
    ]
  }'
```

### Step 3: Create New Cluster

```bash
curl -X POST http://localhost:8000/api/clusters/new \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production",
    "rke2_version": "v1.28.5+rke2r1",
    "credential_id": 1,
    "nodes": [
      {"hostname": "server-1", "ip": "192.168.1.10", "role": "server"},
      {"hostname": "server-2", "ip": "192.168.1.11", "role": "server"},
      {"hostname": "server-3", "ip": "192.168.1.12", "role": "server"},
      {"hostname": "agent-1", "ip": "192.168.1.20", "role": "agent"},
      {"hostname": "agent-2", "ip": "192.168.1.21", "role": "agent"}
    ],
    "registry_mode": "internet"
  }'
```

### Step 4: Install Cluster

```bash
curl -X POST http://localhost:8000/api/jobs/install/1
```

### Step 5: Monitor Installation

```bash
# Get job details
curl http://localhost:8000/api/jobs/1

# Or watch live via frontend
open http://localhost:3000/jobs/1
```

---

## Register Existing Cluster

### 1. Register Cluster

```bash
curl -X POST http://localhost:8000/api/clusters/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "existing-cluster",
    "target_rke2_version": "v1.29.0+rke2r1",
    "kubeconfig": "apiVersion: v1\nkind: Config\n..."
  }'
```

### 2. Run Upgrade Readiness Check

```bash
curl -X POST http://localhost:8000/api/jobs/upgrade-check \
  -H "Content-Type: application/json" \
  -d '{"cluster_id": 2}'
```

### 3. View Results with LLM Summary

```bash
curl http://localhost:8000/api/jobs/2
```

---

## Web UI Workflow

### Option 1: Via UI (Recommended)

1. **Create Credential** (Coming soon - for now use API)
   ```bash
   curl -X POST http://localhost:8000/api/credentials ...
   ```

2. **New Cluster**
   - Go to http://localhost:3000/new-cluster
   - Fill in cluster details
   - Add nodes
   - Review & Create

3. **Install Cluster**
   - Go to http://localhost:3000/clusters
   - Click "Install" on your cluster
   - Monitor progress in real-time

4. **View Jobs**
   - Go to http://localhost:3000/jobs
   - Click job to see Ansible output

---

## API Endpoints

### Credentials
- `POST /api/credentials` - Create credential
- `GET /api/credentials` - List credentials
- `GET /api/credentials/{id}` - Get credential
- `DELETE /api/credentials/{id}` - Delete credential
- `POST /api/credentials/test-access` - Test SSH access

### Clusters
- `POST /api/clusters/new` - Create new cluster
- `POST /api/clusters/register` - Register existing cluster
- `GET /api/clusters` - List clusters
- `GET /api/clusters/{id}` - Get cluster
- `DELETE /api/clusters/{id}` - Delete cluster

### Jobs
- `POST /api/jobs/install/{cluster_id}` - Start installation
- `POST /api/jobs/upgrade-check` - Run upgrade check
- `GET /api/jobs` - List jobs
- `GET /api/jobs/{id}` - Get job details
- `GET /api/jobs/{id}/stream` - Stream job output (SSE)

### Health
- `GET /api/health` - Health check

---

## File Locations

### Generated Cluster Artifacts
```
ansible/clusters/{cluster-name}/
├── inventory.ini        # Ansible inventory
├── rke2-config.yaml    # RKE2 configuration
├── group_vars.yml      # Ansible group variables
└── kubeconfig          # Generated after installation
```

### Playbooks
```
ansible/playbooks/
├── install_rke2.yml       # RKE2 installation
├── check_access.yml       # Pre-flight access check
└── pre_upgrade_check.yml  # Upgrade readiness check
```

### Database
```
data/rke2.db  # SQLite database (credentials, clusters, jobs)
```

---

## Troubleshooting

### Reset Database
```bash
docker-compose down
rm -rf data/rke2.db
docker-compose up -d
# Recreate credentials
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f ansible-runner
```

### Check Ansible Runner
```bash
docker exec -it rke2-automation-ansible-runner-1 /bin/bash
ansible --version
ansible-playbook --help
```

### Manual Playbook Execution
```bash
docker exec rke2-automation-ansible-runner-1 \
  ansible-playbook \
  /ansible/playbooks/check_access.yml \
  -i /ansible/clusters/test-cluster/inventory.ini
```

---

## Security Notes

1. **Encryption Key**: Store securely, rotate periodically
2. **SSH Keys**: Use separate keys per environment
3. **Credentials**: Delete unused credentials
4. **Network**: Run on isolated admin network
5. **Database**: Backup regularly (contains encrypted credentials)

---

## Next Steps

1. **Add Credential UI**: Frontend for credential management
2. **Add Access Check UI**: Pre-flight validation before install
3. **Job Streaming**: Real-time Ansible output in UI
4. **Cluster Details Page**: View inventory, config, job history
5. **Multi-cluster Dashboard**: Overview of all clusters
