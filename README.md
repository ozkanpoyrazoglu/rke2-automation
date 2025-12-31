# RKE2 Automation Tool

Internal tool for managing RKE2/Kubernetes clusters on on-premise infrastructure.

## Features

### Cluster Management
- 🚀 **Create & Install** - Bootstrap new RKE2 clusters with Ansible automation
- 📊 **Monitor Status** - Real-time cluster health, node status, and component monitoring
- 🔧 **Scale Clusters** - Add/remove nodes with safety guardrails
- 📋 **Register Existing** - Import and manage existing RKE2 clusters

### Safety & Reliability
- 🔒 **Cluster Locking** - Prevents concurrent operations (409 Conflict responses)
- ✅ **Guardrails** - Prevents unsafe operations:
  - G1: Bootstrap prerequisite checks
  - G2: Safe master removal (quorum protection)
  - G3: Sequential master/worker additions
  - G4: Node identity validation (no duplicates)
- 🔄 **Node Status Sync** - Auto-sync database with actual cluster state

### User Experience
- 🎨 **Modern UI** - Custom modal dialogs instead of browser alerts
- 📝 **Detailed Error Messages** - Clear, actionable error feedback
- 🔐 **Secure Credentials** - Encrypted SSH credential storage
- 📡 **Live Job Streaming** - Real-time Ansible playbook output

### Advanced Features
- 🤖 **LLM-powered Summaries** - AWS Bedrock (Claude) for job analysis
- 📈 **Upgrade Readiness** - Analyze cluster upgrade compatibility
- 📦 **Cluster Templates** - Role-based RKE2 config generation

## Quick Start

### Prerequisites
- Docker & Docker Compose
- SSH access to target nodes
- (Optional) AWS credentials for LLM features

### Setup

1. **Clone and configure:**
```bash
git clone <repository-url>
cd rke2-automation
cp .env.example .env
# Edit .env with your AWS credentials and encryption key
```

2. **Start services:**
```bash
docker-compose up -d
```

3. **Access UI:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Configuration

Generate encryption key for credentials:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add to `.env`:
```env
ENCRYPTION_KEY=your-generated-key-here
```

## Architecture

### Stack
- **Frontend:** React + Vite (port 3000)
- **Backend:** FastAPI + SQLAlchemy (port 8000)
- **Database:** SQLite (persistent volume)
- **Automation:** Ansible + ansible-runner
- **AI/LLM:** AWS Bedrock (Claude Sonnet)

### Data Storage
- Database: `./data/rke2.db` (SQLite)
- Ansible artifacts: `./ansible/clusters/<cluster-name>/`
- Credentials: Encrypted in database

### Security
- SSH credentials encrypted with Fernet
- Kubeconfigs stored in database
- Sensitive files excluded via `.gitignore`
- No hardcoded credentials

## Usage

### Creating a Cluster

1. Navigate to **Clusters** → **New Cluster**
2. Fill in cluster details:
   - Name, RKE2 version, CNI plugin
   - Initial master node info
3. Add SSH credentials
4. Click **Create Cluster** (generates Ansible artifacts)
5. Click **Install** to start deployment

### Scaling Clusters

**Add Nodes:**
1. Go to cluster detail page → **Scale** tab
2. Enter node hostname, IP, and role (server/agent)
3. Click **Add Node**

**Remove Nodes:**
1. Select nodes to remove
2. Click **Remove Selected**
3. Confirm deletion (drains and uninstalls RKE2)

### Monitoring

- **Overview Tab:** Cluster status, component health, node list
- **Jobs Tab:** View installation/scaling job logs
- **Status Refresh:** Auto-syncs node statuses from Kubernetes

## API Guardrails

The system prevents unsafe operations:

**409 Conflict:**
```json
{
  "detail": "Cluster is busy with operation 'scale_add_workers' (job 42). Please wait for it to complete."
}
```

**400 Bad Request:**
```json
{
  "detail": "Initial master must be ACTIVE before adding nodes"
}
```

See [CLUSTER_LOCK_AND_GUARDRAILS.md](./CLUSTER_LOCK_AND_GUARDRAILS.md) for details.

## Development

### Project Structure
```
.
├── frontend/          # React frontend
├── backend/           # FastAPI backend
│   ├── app/
│   │   ├── routers/   # API endpoints
│   │   ├── services/  # Business logic
│   │   └── models.py  # Database models
├── ansible/           # Ansible playbooks
└── data/              # SQLite database (gitignored)
```

### Running Locally
```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Troubleshooting

**Cluster shows PENDING but is actually ACTIVE:**
- Use **Sync Nodes** button on cluster detail page
- Auto-sync happens on status refresh

**Node addition fails with 409:**
- Another operation is running - wait for it to complete
- Check **Jobs** page for running jobs

**SSH connection fails:**
- Verify credentials in **Credentials** page
- Check node firewalls (port 22)
- Test SSH manually: `ssh user@node-ip`

## License

Internal use only.

## Documentation

- [Cluster Lock & Guardrails](./CLUSTER_LOCK_AND_GUARDRAILS.md)
- [RKE2 Config Fix Summary](./RKE2_CONFIG_FIX_SUMMARY.md)
