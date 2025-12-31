# RKE2 Automation - Architecture

## Directory Structure

```
rke2-automation/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── database.py        # SQLAlchemy setup
│   │   ├── models.py          # Database models (Cluster, Job)
│   │   ├── schemas.py         # Pydantic schemas
│   │   ├── routers/
│   │   │   ├── health.py      # Health check endpoint
│   │   │   ├── clusters.py    # Cluster CRUD endpoints
│   │   │   └── jobs.py        # Job execution endpoints
│   │   └── services/
│   │       ├── cluster_service.py       # Cluster creation logic
│   │       ├── ansible_generator.py     # Generate Ansible artifacts
│   │       ├── ansible_service.py       # Execute playbooks
│   │       ├── readiness_service.py     # Upgrade checks
│   │       └── llm_service.py           # Bedrock integration
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                   # React + Vite UI
│   ├── src/
│   │   ├── main.jsx           # React entry point
│   │   ├── App.jsx            # Router and layout
│   │   ├── api.js             # API client
│   │   ├── index.css          # Styles (AWX-like)
│   │   └── pages/
│   │       ├── Dashboard.jsx
│   │       ├── Clusters.jsx
│   │       ├── NewCluster.jsx
│   │       ├── RegisterCluster.jsx
│   │       ├── Jobs.jsx
│   │       └── JobDetail.jsx
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.js
│
├── ansible/
│   ├── playbooks/
│   │   ├── install_rke2.yml        # RKE2 installation
│   │   └── pre_upgrade_check.yml   # Pre-upgrade checks
│   └── clusters/                    # Generated per-cluster artifacts
│       └── {cluster-name}/
│           ├── inventory.ini
│           ├── rke2-config.yaml
│           ├── group_vars.yml
│           └── kubeconfig
│
├── data/                       # SQLite database (gitignored)
│   └── rke2.db
│
├── docs/
│   ├── ARCHITECTURE.md         # This file
│   ├── example-readiness-output.json
│   └── llm-prompt-example.md
│
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Data Flow

### 1. New Cluster Creation

```
User fills wizard → POST /api/clusters/new
  ↓
Backend creates Cluster record (type=new)
  ↓
ansible_generator creates:
  - inventory.ini
  - rke2-config.yaml
  - group_vars.yml
  ↓
User clicks "Install" → POST /api/jobs/install/{cluster_id}
  ↓
Background task executes install_rke2.yml
  ↓
ansible-runner streams output → Job.output
  ↓
User views live output via SSE endpoint
```

### 2. Cluster Registration + Upgrade Check

```
User uploads kubeconfig → POST /api/clusters/register
  ↓
Backend creates Cluster record (type=registered)
  ↓
Kubeconfig saved to filesystem
  ↓
User clicks "Check Upgrade" → POST /api/jobs/upgrade-check
  ↓
readiness_service runs checks via kubectl:
  - etcd health (etcdctl)
  - node status (kubectl get nodes)
  - disk usage (df)
  - cert expiration (openssl)
  - deprecated APIs (pluto or kubectl)
  ↓
Results stored in Job.readiness_json
  ↓
LLM prompt sent to Bedrock with readiness JSON
  ↓
Bedrock returns markdown summary → Job.llm_summary
  ↓
User views results in JobDetail page
```

## Key Design Decisions

### Backend

- **FastAPI**: Modern, async, auto-generated OpenAPI docs
- **SQLite**: Simple local storage, no external dependencies
- **ansible-runner**: Official Ansible Python API
- **Pydantic**: Type-safe request/response validation
- **SSE**: Server-sent events for live output streaming

### Frontend

- **React + Vite**: Fast dev experience, minimal boilerplate
- **No UI framework**: Custom CSS for lightweight, AWX-inspired design
- **React Router**: Client-side routing
- **Axios**: HTTP client with simple API wrapper

### Ansible

- **Jinja2 templates**: Generate inventory and config files
- **Idempotent playbooks**: Safe to re-run
- **Separate playbooks**: Install vs checks, clear separation of concerns

### LLM Integration

- **AWS Bedrock**: Managed service, no infrastructure
- **Claude 3.5 Sonnet**: Balanced speed/quality for summaries
- **Structured input**: JSON readiness data → LLM → markdown summary
- **Fallback**: If Bedrock fails, show raw JSON

## Security Considerations

- Kubeconfigs stored on filesystem (0600 permissions)
- SSH keys managed outside this tool (user responsibility)
- No multi-tenancy (single admin machine)
- Secrets in environment variables (AWS credentials)

## Future Enhancements (Post-MVP)

- PostgreSQL instead of SQLite
- WebSocket instead of SSE polling
- Ansible callback plugins for better streaming
- Cert expiration parsing from actual cluster certs
- Integration with Prometheus/Grafana for disk metrics
- Support for multiple Kubernetes distributions
