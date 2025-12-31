# Credentials & Access Validation

## Overview

Enhanced security and pre-flight validation layer for RKE2 cluster operations.

## Components

### 1. Ansible Runner Container

**Purpose:** Dedicated execution environment for Ansible playbooks

**Location:** [ansible-runner/Dockerfile](../ansible-runner/Dockerfile)

**Includes:**
- ansible 9.1.0
- ansible-runner 2.3.6
- openssh-client
- sshpass (for password auth)

**Access:** Backend communicates via `docker exec`

### 2. Credential Model

**Database Table:** `credentials`

**Fields:**
- `id`: Primary key
- `name`: Unique credential name
- `username`: SSH username
- `credential_type`: `ssh_key` or `ssh_password`
- `encrypted_secret`: Fernet-encrypted private key or password

**Security:**
- Secrets encrypted at rest using `ENCRYPTION_KEY` env var
- Never logged or exposed in API responses
- Temp files created only during execution (0600 perms)
- Temp files securely deleted after use

**API Endpoints:**
```
POST   /api/credentials          Create credential
GET    /api/credentials          List credentials (no secrets)
GET    /api/credentials/{id}     Get credential (no secret)
DELETE /api/credentials/{id}     Delete credential
POST   /api/credentials/test-access    Test access to hosts
```

### 3. Access Check Playbook

**Location:** [ansible/playbooks/check_access.yml](../ansible/playbooks/check_access.yml)

**Validates:**
- ✓ SSH connectivity
- ✓ Sudo/privilege escalation
- ✓ OS compatibility (Ubuntu/RHEL/Rocky/CentOS)
- ✓ Disk space warning (>80%)

**Outputs:**
- Per-host status (ok/failed)
- Clear error messages
- Structured summary

**Fail-fast:** Blocks execution if critical checks fail

### 4. Encryption Service

**Location:** [backend/app/services/encryption_service.py](../backend/app/services/encryption_service.py)

**Functions:**
- `encrypt_secret(plaintext)` → encrypted string
- `decrypt_secret(encrypted)` → plaintext string

**Algorithm:** Fernet (symmetric encryption)

**Key Management:**
- Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Store in `.env` as `ENCRYPTION_KEY`
- Rotate: Re-encrypt all credentials with new key

### 5. Credential Injection

**Flow:**

```
Job triggered → Load credential from DB
              ↓
          Decrypt secret
              ↓
    Write to temp file (/tmp/ansible/*.key)
              ↓
    Pass to ansible-playbook via --private-key
              ↓
    Execute playbook in ansible-runner container
              ↓
    Securely delete temp file (os.remove)
```

**Location:** [backend/app/services/ansible_service.py](../backend/app/services/ansible_service.py)

## Usage Examples

### 1. Create SSH Key Credential

```bash
# Generate key pair
ssh-keygen -t ed25519 -f ~/.ssh/rke2_key -N ""

# Read private key
cat ~/.ssh/rke2_key

# POST to API
curl -X POST http://localhost:8000/api/credentials \
  -H "Content-Type: application/json" \
  -d '{
    "name": "prod-ssh-key",
    "username": "ubuntu",
    "credential_type": "ssh_key",
    "secret": "-----BEGIN OPENSSH PRIVATE KEY-----\n..."
  }'
```

### 2. Test Access Before Cluster Creation

```bash
curl -X POST http://localhost:8000/api/credentials/test-access \
  -H "Content-Type: application/json" \
  -d '{
    "credential_id": 1,
    "hosts": [
      {"hostname": "node-1", "ip": "192.168.1.10"},
      {"hostname": "node-2", "ip": "192.168.1.11"}
    ]
  }'
```

**Response:**
```json
{
  "overall_status": "success",
  "results": [
    {
      "hostname": "node-1",
      "ip": "192.168.1.10",
      "status": "ok",
      "ssh_reachable": true,
      "sudo_available": true,
      "os_compatible": true,
      "error": null
    },
    {
      "hostname": "node-2",
      "ip": "192.168.1.11",
      "status": "failed",
      "ssh_reachable": true,
      "sudo_available": false,
      "os_compatible": true,
      "error": "Sudo check failed"
    }
  ]
}
```

### 3. Create Cluster with Credential

```bash
curl -X POST http://localhost:8000/api/clusters/new \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production",
    "rke2_version": "v1.28.5+rke2r1",
    "credential_id": 1,
    "nodes": [
      {"hostname": "server-1", "ip": "192.168.1.10", "role": "server"},
      {"hostname": "agent-1", "ip": "192.168.1.20", "role": "agent"}
    ],
    "registry_mode": "internet"
  }'
```

## Security Best Practices

1. **Encryption Key:**
   - Generate strong key using Fernet
   - Store in `.env`, never commit to git
   - Rotate periodically

2. **SSH Keys:**
   - Use ed25519 or RSA 4096-bit keys
   - Prefer key-based auth over passwords
   - Use separate keys per environment

3. **Access Control:**
   - Limit SSH user privileges (use sudo, not root login)
   - Disable password auth on target hosts
   - Use bastion/jump hosts for production

4. **Credential Lifecycle:**
   - Delete unused credentials
   - Check "in use" before deletion (prevents orphaned clusters)
   - Audit credential usage via job logs

## Troubleshooting

### "Unable to decrypt credential"
- Check `ENCRYPTION_KEY` env var is set
- Verify key hasn't changed since credential creation
- Re-encrypt credentials if key rotated

### "SSH connection failed" during access check
- Verify target host is reachable from ansible-runner container
- Check SSH key permissions (must be 0600)
- Ensure SSH service running on target
- Verify username matches target system

### "Sudo check failed"
- User needs passwordless sudo: `ubuntu ALL=(ALL) NOPASSWD:ALL`
- Edit `/etc/sudoers.d/` on target hosts

### "OS not compatible"
- Supported: Ubuntu, Debian, RHEL, CentOS, Rocky Linux
- Update playbook for other distributions
