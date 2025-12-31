# Frontend UI Features Guide

## Complete Feature List

### ✅ 1. Credentials Management
**Page:** `/credentials`

**Features:**
- View all SSH credentials
- Create new credentials (SSH key or password)
- Delete unused credentials
- Credential type badges (SSH Key / Password)
- Warning when credentials are in use

**How to Use:**
1. Click **Credentials** in sidebar
2. Click **+ New Credential**
3. Fill in:
   - Name (e.g., "production-key")
   - Username (e.g., "ubuntu")
   - Type (SSH Key recommended)
   - Private key or password
4. Click **Create Credential**

---

### ✅ 2. New Cluster Wizard with Credential Selection
**Page:** `/new-cluster`

**Step 1: Basic Configuration**
- Cluster name
- RKE2 version
- **SSH Credential dropdown** (auto-loads available credentials)
- Registry mode (internet/airgap/custom)
- Custom registry URL (if needed)

**Step 2: Add Nodes**
- Add multiple nodes
- Per-node configuration:
  - Hostname
  - IP address
  - Role (server/agent)
- **"Test SSH Access" button** for pre-flight validation
- Real-time access check results table:
  - SSH connectivity ✓/✗
  - Sudo availability ✓/✗
  - OS compatibility ✓/✗
  - Error messages if any

**Step 3: Review & Create**
- Summary of all settings
- Node list with roles
- Create cluster button

---

### ✅ 3. Test Access Feature
**Location:** New Cluster wizard - Step 2

**What it does:**
- Tests SSH connectivity to all nodes
- Validates sudo permissions
- Checks OS compatibility
- Shows results in a table with color-coded badges

**How to Use:**
1. Add all your nodes in Step 2
2. Fill in hostnames and IPs
3. Click **"Test SSH Access"** button
4. Review results:
   - Green badges (✓) = passed
   - Red badges (✗) = failed
   - Error messages explain failures

**Benefits:**
- Catch configuration errors early
- Verify credentials work before installation
- Validate sudo permissions
- Ensure OS compatibility

---

### ✅ 4. Real-time Job Streaming
**Page:** `/jobs/{id}`

**Features:**
- Live Ansible output streaming (SSE)
- Auto-scroll to latest output
- "● LIVE" indicator when streaming
- Persistent output after job completion
- Job status badges (pending/running/success/failed)
- Timestamps for started/completed

**How to Use:**
1. Start a cluster installation from `/clusters`
2. Click on the job ID or navigate to Jobs page
3. View live output as Ansible executes
4. Terminal auto-scrolls to show latest output
5. Output persists after job completes

**Technical Details:**
- Uses Server-Sent Events (SSE)
- Endpoint: `GET /api/jobs/{id}/stream`
- Auto-reconnects on connection loss
- Polls job status every 3 seconds

---

### ✅ 5. Clusters Management
**Page:** `/clusters`

**Features:**
- List all clusters (new + registered)
- Cluster type badges
- Install button for new clusters
- Upgrade check button for registered clusters
- Delete cluster

**Actions:**
- **Install**: Starts Ansible playbook execution
- **Check Upgrade**: Runs readiness analysis
- **Delete**: Removes cluster and all related data

---

### ✅ 6. Jobs Dashboard
**Page:** `/jobs`

**Features:**
- List all jobs across all clusters
- Filter by cluster
- Job type (install / upgrade_check)
- Status badges with colors
- Duration calculation
- Quick link to job details

---

### ✅ 7. Dashboard
**Page:** `/`

**Features:**
- Total clusters count
- New clusters count
- Registered clusters count
- Recent jobs table (last 5)
- Quick navigation to job details

---

## Navigation Menu

```
Dashboard          → /
Credentials        → /credentials
Clusters          → /clusters
New Cluster       → /new-cluster
Register Cluster  → /register-cluster
Jobs             → /jobs
```

---

## Color Scheme & Badges

### Status Colors
- **Success** (green): Completed successfully
- **Danger** (red): Failed
- **Info** (blue): Running
- **Warning** (yellow): Pending

### Credential Types
- **SSH Key** (green badge): Recommended
- **Password** (yellow badge): Not recommended

### Role Badges
- **Server** (blue): Control plane nodes
- **Agent** (green): Worker nodes

---

## User Flow Examples

### Example 1: Create New Cluster
1. Go to **Credentials** → Create SSH key credential
2. Go to **New Cluster**
3. Step 1: Enter name, version, select credential
4. Step 2: Add nodes (hostname, IP, role)
5. Click **Test SSH Access** → Verify all checks pass
6. Step 3: Review and create
7. Go to **Clusters** → Click **Install**
8. Monitor progress in real-time on job detail page

### Example 2: Register & Check Upgrade
1. Go to **Register Cluster**
2. Upload kubeconfig
3. Set target RKE2 version
4. Click Register
5. Go to **Clusters** → Click **Check Upgrade**
6. View readiness results + LLM summary

---

## Keyboard Shortcuts & UX

- Forms validate required fields
- Buttons disable when invalid
- Auto-scroll on live output
- Confirmation dialogs for destructive actions
- Error messages show API errors
- Loading states during async operations

---

## API Integration

All UI features call backend APIs:

```javascript
// Credentials
GET    /api/credentials
POST   /api/credentials
DELETE /api/credentials/{id}
POST   /api/credentials/test-access

// Clusters
GET    /api/clusters
POST   /api/clusters/new
POST   /api/clusters/register
DELETE /api/clusters/{id}

// Jobs
GET    /api/jobs
GET    /api/jobs/{id}
GET    /api/jobs/{id}/stream (SSE)
POST   /api/jobs/install/{cluster_id}
POST   /api/jobs/upgrade-check
```

---

## Browser Compatibility

Tested on:
- Chrome/Edge (recommended)
- Firefox
- Safari

**Requirements:**
- JavaScript enabled
- EventSource API support (for SSE streaming)
- Modern browser (ES6+ support)

---

## What's Next?

Future enhancements:
- Credential test on creation
- Bulk node import (CSV)
- Cluster health dashboard
- Job retry functionality
- Multi-cluster operations
- Export job logs
- Dark mode
