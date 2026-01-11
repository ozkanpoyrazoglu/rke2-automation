import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AlertModal, ConfirmModal } from '../components/Modal'

export default function ClusterDetail() {
  const { clusterId } = useParams()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('overview')
  const [cluster, setCluster] = useState(null)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [statusLoading, setStatusLoading] = useState(false)
  const [fetchingKubeconfig, setFetchingKubeconfig] = useState(false)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [kubeconfigContent, setKubeconfigContent] = useState('')
  const [scaleInfo, setScaleInfo] = useState(null)
  const [newNodeForm, setNewNodeForm] = useState({ hostname: '', ip: '', external_ip: '', role: 'agent', use_external_ip: false })
  const [selectedNodes, setSelectedNodes] = useState([])
  const [scaleLoading, setScaleLoading] = useState(false)

  // Upgrade readiness states
  const [preflightLoading, setPreflightLoading] = useState(false)
  const [upgradeJobs, setUpgradeJobs] = useState([])
  const [selectedJob, setSelectedJob] = useState(null)
  const [jobPolling, setJobPolling] = useState(null)
  const [aiSelectionModalOpen, setAiSelectionModalOpen] = useState(false)
  const [useAiAnalysis, setUseAiAnalysis] = useState(true)
  const [targetVersion, setTargetVersion] = useState('')

  // Modal states
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info' })
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null, type: 'warning' })

  useEffect(() => {
    loadCluster()
  }, [clusterId])

  useEffect(() => {
    if (activeTab === 'overview' && cluster?.kubeconfig) {
      loadStatus()
    }
    if (activeTab === 'scale' && cluster?.cluster_type === 'new') {
      loadScaleInfo()
    }
    if (activeTab === 'upgrade') {
      loadUpgradeJobs()
    }
  }, [activeTab, cluster?.kubeconfig, cluster?.cluster_type])

  // Cleanup job polling on unmount
  useEffect(() => {
    return () => {
      if (jobPolling) clearInterval(jobPolling)
    }
  }, [jobPolling])

  const loadCluster = () => {
    fetch(`http://localhost:8000/api/clusters/${clusterId}`)
      .then(res => res.json())
      .then(data => {
        console.log('Cluster loaded:', data)
        console.log('Has kubeconfig:', !!data.kubeconfig)
        setCluster(data)
        setLoading(false)
      })
      .catch(err => {
        setAlertModal({
          isOpen: true,
          title: 'Error',
          message: `Error loading cluster: ${err.message}`,
          type: 'error'
        })
        setTimeout(() => navigate('/clusters'), 2000)
      })
  }

  const loadStatus = (forceRefresh = false) => {
    if (!cluster?.kubeconfig) {
      console.log('No kubeconfig available, skipping status load')
      return
    }

    setStatusLoading(true)

    // Use refresh endpoint if force refresh requested
    const endpoint = forceRefresh
      ? `http://localhost:8000/api/clusters/${clusterId}/refresh`
      : `http://localhost:8000/api/clusters/${clusterId}/status`

    const method = forceRefresh ? 'POST' : 'GET'

    fetch(endpoint, { method })
      .then(res => res.json())
      .then(data => {
        setStatus(data)
        setStatusLoading(false)
      })
      .catch(err => {
        console.error('Failed to load status:', err)
        setStatusLoading(false)
      })
  }

  const handleFetchKubeconfig = () => {
    setConfirmModal({
      isOpen: true,
      title: 'Fetch Kubeconfig',
      message: 'Fetch kubeconfig from master node via SSH?',
      type: 'info',
      onConfirm: () => {
        setFetchingKubeconfig(true)
        fetch(`http://localhost:8000/api/clusters/${clusterId}/fetch-kubeconfig`, {
          method: 'POST'
        })
          .then(async res => {
            const data = await res.json()
            if (!res.ok) {
              throw new Error(data.detail || 'Failed to fetch kubeconfig')
            }
            return data
          })
          .then(data => {
            setAlertModal({
              isOpen: true,
              title: 'Success',
              message: 'Kubeconfig fetched successfully',
              type: 'success'
            })
            loadCluster()
            setFetchingKubeconfig(false)
          })
          .catch(err => {
            setAlertModal({
              isOpen: true,
              title: 'Error',
              message: err.message,
              type: 'error'
            })
            setFetchingKubeconfig(false)
          })
      }
    })
  }

  const handleUploadKubeconfig = () => {
    if (!kubeconfigContent.trim()) {
      setAlertModal({
        isOpen: true,
        title: 'Validation Error',
        message: 'Please paste kubeconfig content',
        type: 'warning'
      })
      return
    }

    fetch(`http://localhost:8000/api/clusters/${clusterId}/upload-kubeconfig`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: kubeconfigContent })
    })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) {
          throw new Error(data.detail || 'Failed to upload kubeconfig')
        }
        return data
      })
      .then(data => {
        setAlertModal({
          isOpen: true,
          title: 'Success',
          message: 'Kubeconfig uploaded successfully',
          type: 'success'
        })
        setUploadModalOpen(false)
        setKubeconfigContent('')
        loadCluster()
      })
      .catch(err => {
        setAlertModal({
          isOpen: true,
          title: 'Error',
          message: err.message,
          type: 'error'
        })
      })
  }

  const handleSaveEdit = (e) => {
    e.preventDefault()
    fetch(`http://localhost:8000/api/clusters/${clusterId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: cluster.name,
        rke2_version: cluster.rke2_version,
        cni: cluster.cni,
        rke2_data_dir: cluster.rke2_data_dir,
        rke2_api_ip: cluster.rke2_api_ip,
        rke2_token: cluster.rke2_token,
        rke2_additional_sans: cluster.rke2_additional_sans
      })
    })
      .then(res => res.json())
      .then(data => {
        setAlertModal({
          isOpen: true,
          title: 'Success',
          message: 'Cluster updated successfully',
          type: 'success'
        })
        setCluster(data)
      })
      .catch(err => {
        setAlertModal({
          isOpen: true,
          title: 'Error',
          message: err.message,
          type: 'error'
        })
      })
  }

  const loadScaleInfo = () => {
    fetch(`http://localhost:8000/api/clusters/${clusterId}/scale`)
      .then(res => res.json())
      .then(data => setScaleInfo(data))
      .catch(err => console.error('Failed to load scale info:', err))
  }

  const handleAddNode = () => {
    if (!newNodeForm.hostname || !newNodeForm.ip) {
      setAlertModal({
        isOpen: true,
        title: 'Validation Error',
        message: 'Please fill in hostname and internal IP',
        type: 'warning'
      })
      return
    }

    // Prepare node data - use external IP for Ansible if checkbox is checked and external IP exists
    const nodeData = {
      hostname: newNodeForm.hostname,
      ip: newNodeForm.use_external_ip && newNodeForm.external_ip ? newNodeForm.external_ip : newNodeForm.ip,
      internal_ip: newNodeForm.ip,
      external_ip: newNodeForm.external_ip || null,
      role: newNodeForm.role
    }

    setScaleLoading(true)
    fetch(`http://localhost:8000/api/clusters/${clusterId}/scale/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes: [nodeData] })
    })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) {
          // Handle error responses (400, 409, 500, etc.)
          throw new Error(data.detail || `Server error: ${res.status}`)
        }
        return data
      })
      .then(data => {
        setAlertModal({
          isOpen: true,
          title: 'Job Created',
          message: data.message,
          type: 'success'
        })
        setNewNodeForm({ hostname: '', ip: '', external_ip: '', role: 'agent', use_external_ip: false })
        setScaleLoading(false)
        setTimeout(() => navigate(`/jobs/${data.job_id}`), 1500)
      })
      .catch(err => {
        setAlertModal({
          isOpen: true,
          title: 'Error',
          message: err.message,
          type: 'error'
        })
        setScaleLoading(false)
      })
  }

  // Upgrade readiness functions
  const loadUpgradeJobs = () => {
    fetch(`http://localhost:8000/api/jobs?cluster_id=${clusterId}`)
      .then(res => res.json())
      .then(data => {
        const filtered = data.filter(j => ['preflight_check', 'upgrade_check'].includes(j.job_type))
        filtered.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        setUpgradeJobs(filtered)
      })
      .catch(err => console.error('Failed to load upgrade jobs:', err))
  }

  const loadJobDetail = (jobId) => {
    fetch(`http://localhost:8000/api/jobs/${jobId}`)
      .then(res => res.json())
      .then(data => {
        setSelectedJob(data)
        if (data.status === 'running') {
          startJobPolling(jobId)
        }
      })
      .catch(err => console.error('Failed to load job detail:', err))
  }

  const startJobPolling = (jobId) => {
    if (jobPolling) clearInterval(jobPolling)
    const interval = setInterval(() => {
      fetch(`http://localhost:8000/api/jobs/${jobId}`)
        .then(res => res.json())
        .then(data => {
          setSelectedJob(data)
          if (data.status !== 'running') {
            clearInterval(interval)
            setJobPolling(null)
            loadUpgradeJobs()
          }
        })
        .catch(err => console.error('Polling error:', err))
    }, 2000)
    setJobPolling(interval)
  }

  const handleNewPreflightCheck = () => {
    setAiSelectionModalOpen(true)
  }

  const handleConfirmPreflightCheck = () => {
    setAiSelectionModalOpen(false)
    setPreflightLoading(true)

    // Build URL with query parameters
    let url = `http://localhost:8000/api/clusters/${clusterId}/preflight-check`
    const params = []
    if (useAiAnalysis) params.push('analyze=true')
    if (targetVersion.trim()) params.push(`target_version=${encodeURIComponent(targetVersion.trim())}`)
    if (params.length > 0) url += '?' + params.join('&')

    fetch(url, { method: 'POST' })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) {
          throw new Error(data.detail || 'Failed to start preflight check')
        }
        return data
      })
      .then(data => {
        setAlertModal({
          isOpen: true,
          title: 'Check Started',
          message: `Preflight check job #${data.job_id} started`,
          type: 'success'
        })
        setPreflightLoading(false)
        setTargetVersion('') // Reset target version after successful submission
        loadUpgradeJobs()
        setTimeout(() => loadJobDetail(data.job_id), 500)
      })
      .catch(err => {
        setAlertModal({
          isOpen: true,
          title: 'Error',
          message: err.message,
          type: 'error'
        })
        setPreflightLoading(false)
      })
  }

  const handleRemoveNodes = () => {
    if (selectedNodes.length === 0) {
      setAlertModal({
        isOpen: true,
        title: 'No Selection',
        message: 'Please select nodes to remove',
        type: 'warning'
      })
      return
    }

    const nodesToRemove = scaleInfo.nodes.filter(n =>
      selectedNodes.includes(n.hostname)
    ).map(node => ({
      hostname: node.hostname,
      ip: node.internal_ip || node.ip || node.external_ip,  // Prefer internal IP for Ansible
      internal_ip: node.internal_ip,
      external_ip: node.external_ip,
      role: node.role
    }))

    setConfirmModal({
      isOpen: true,
      title: 'Remove Nodes',
      message: `Remove ${selectedNodes.length} node(s)?\n\nThis will drain and uninstall RKE2 from selected nodes.`,
      type: 'danger',
      confirmText: 'Remove',
      onConfirm: () => {
        setScaleLoading(true)
        fetch(`http://localhost:8000/api/clusters/${clusterId}/scale/remove`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nodes: nodesToRemove })
        })
          .then(async res => {
            const data = await res.json()
            if (!res.ok) {
              // Handle error responses (400, 409, 500, etc.)
              throw new Error(data.detail || `Server error: ${res.status}`)
            }
            return data
          })
          .then(data => {
            setAlertModal({
              isOpen: true,
              title: 'Job Created',
              message: data.message,
              type: 'success'
            })
            setSelectedNodes([])
            setScaleLoading(false)
            setTimeout(() => navigate(`/jobs/${data.job_id}`), 1500)
          })
          .catch(err => {
            setAlertModal({
              isOpen: true,
              title: 'Error',
              message: err.message,
              type: 'error'
            })
            setScaleLoading(false)
          })
      }
    })
  }

  if (loading) return <div className="loading">Loading...</div>

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button onClick={() => navigate('/clusters')} className="btn btn-secondary">
            ← Back
          </button>
          <div>
            <h2>{cluster.name}</h2>
            <p>Cluster Details</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ marginBottom: '20px', borderBottom: '2px solid #e2e8f0' }}>
        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            onClick={() => setActiveTab('overview')}
            style={{
              padding: '12px 24px',
              background: activeTab === 'overview' ? '#3b82f6' : 'transparent',
              color: activeTab === 'overview' ? 'white' : '#64748b',
              border: 'none',
              borderBottom: activeTab === 'overview' ? '2px solid #3b82f6' : 'none',
              cursor: 'pointer',
              fontWeight: activeTab === 'overview' ? 'bold' : 'normal',
              borderRadius: '4px 4px 0 0'
            }}
          >
            Overview
          </button>
          <button
            onClick={() => setActiveTab('details')}
            style={{
              padding: '12px 24px',
              background: activeTab === 'details' ? '#3b82f6' : 'transparent',
              color: activeTab === 'details' ? 'white' : '#64748b',
              border: 'none',
              borderBottom: activeTab === 'details' ? '2px solid #3b82f6' : 'none',
              cursor: 'pointer',
              fontWeight: activeTab === 'details' ? 'bold' : 'normal',
              borderRadius: '4px 4px 0 0'
            }}
          >
            Details
          </button>
          <button
            onClick={() => setActiveTab('edit')}
            style={{
              padding: '12px 24px',
              background: activeTab === 'edit' ? '#3b82f6' : 'transparent',
              color: activeTab === 'edit' ? 'white' : '#64748b',
              border: 'none',
              borderBottom: activeTab === 'edit' ? '2px solid #3b82f6' : 'none',
              cursor: 'pointer',
              fontWeight: activeTab === 'edit' ? 'bold' : 'normal',
              borderRadius: '4px 4px 0 0'
            }}
          >
            Edit Cluster
          </button>
          {cluster.cluster_type === 'new' && (
            <button
              onClick={() => setActiveTab('scale')}
              style={{
                padding: '12px 24px',
                background: activeTab === 'scale' ? '#3b82f6' : 'transparent',
                color: activeTab === 'scale' ? 'white' : '#64748b',
                border: 'none',
                borderBottom: activeTab === 'scale' ? '2px solid #3b82f6' : 'none',
                cursor: 'pointer',
                fontWeight: activeTab === 'scale' ? 'bold' : 'normal',
                borderRadius: '4px 4px 0 0'
              }}
            >
              Scale Cluster
            </button>
          )}
          <button
            onClick={() => setActiveTab('upgrade')}
            style={{
              padding: '12px 24px',
              background: activeTab === 'upgrade' ? '#3b82f6' : 'transparent',
              color: activeTab === 'upgrade' ? 'white' : '#64748b',
              border: 'none',
              borderBottom: activeTab === 'upgrade' ? '2px solid #3b82f6' : 'none',
              cursor: 'pointer',
              fontWeight: activeTab === 'upgrade' ? 'bold' : 'normal',
              borderRadius: '4px 4px 0 0'
            }}
          >
            Upgrade Readiness
          </button>
        </div>
      </div>

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div>
          {/* Cluster Connection Info */}
          {cluster.cluster_type === 'new' && (
            <div className="card" style={{ marginBottom: '20px' }}>
              <h4 style={{ marginBottom: '16px' }}>Cluster Connection Info</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', color: '#64748b' }}>
                    API Server
                  </label>
                  <code style={{ display: 'block', padding: '8px', background: '#f1f5f9', borderRadius: '4px', fontSize: '14px' }}>
                    https://{cluster.rke2_api_ip || 'not-set'}:9345
                  </code>
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', color: '#64748b' }}>
                    Join Token
                  </label>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <code style={{ flex: 1, padding: '8px', background: '#f1f5f9', borderRadius: '4px', fontSize: '14px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {cluster.rke2_token || 'not-set'}
                    </code>
                    {cluster.rke2_token && (
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(cluster.rke2_token)
                          setAlertModal({
                            isOpen: true,
                            title: 'Copied',
                            message: 'Token copied to clipboard',
                            type: 'success'
                          })
                        }}
                        className="btn btn-secondary"
                        style={{ padding: '8px 12px', fontSize: '12px' }}
                      >
                        Copy
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Kubeconfig Section */}
          {!cluster.kubeconfig && (
            <div className="card" style={{ background: '#fef3c7', border: '1px solid #fbbf24', marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ margin: 0, marginBottom: '8px', color: '#92400e' }}>No Kubeconfig Found</h4>
                  <p style={{ margin: 0, color: '#92400e' }}>
                    Fetch kubeconfig from master node or upload manually to view cluster status.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  {cluster.cluster_type === 'new' && (
                    <button
                      onClick={handleFetchKubeconfig}
                      className="btn btn-primary"
                      disabled={fetchingKubeconfig}
                    >
                      {fetchingKubeconfig ? 'Fetching...' : 'Fetch from Master'}
                    </button>
                  )}
                  <button onClick={() => setUploadModalOpen(true)} className="btn btn-secondary">
                    Upload Kubeconfig
                  </button>
                </div>
              </div>
            </div>
          )}

          {cluster.kubeconfig && (
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0 }}>Kubernetes Status</h3>
                <p style={{ margin: 0, color: '#64748b', fontSize: '14px' }}>
                  Kubeconfig: ✓ Available
                  {status?._cache_metadata && (
                    <span style={{ marginLeft: '12px', color: '#94a3b8' }}>
                      • Cached (expires {new Date(status._cache_metadata.expires_at).toLocaleTimeString()})
                    </span>
                  )}
                </p>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button onClick={() => loadStatus(true)} className="btn btn-secondary" disabled={statusLoading}>
                  {statusLoading ? 'Refreshing...' : 'Force Refresh'}
                </button>
              </div>
            </div>
          )}

          {!cluster.kubeconfig && (
            <div className="card" style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
              <p style={{ margin: 0, fontSize: '18px' }}>Configure kubeconfig to view cluster status</p>
            </div>
          )}

          {cluster.kubeconfig && statusLoading && <div className="loading">Loading status...</div>}

          {cluster.kubeconfig && !statusLoading && status?.error && (
            <div className="card" style={{ background: '#fef2f2', border: '1px solid #fecaca' }}>
              <p style={{ color: '#dc2626', margin: 0 }}>{status.error}</p>
            </div>
          )}

          {cluster.kubeconfig && !statusLoading && status && !status.error && (
            <div style={{ display: 'grid', gap: '16px' }}>
              {/* Kubernetes Version */}
              <div className="card">
                <h4 style={{ marginBottom: '12px' }}>Kubernetes Version</h4>
                <p style={{ fontSize: '20px', fontWeight: 'bold', color: '#3b82f6', margin: 0 }}>
                  {status.cluster_metadata?.kubernetes_version || status.kubernetes_version || 'Unknown'}
                </p>
              </div>

              {/* Nodes Summary */}
              <div className="card">
                <h4 style={{ marginBottom: '12px' }}>Nodes</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Total</p>
                    <p style={{ fontSize: '24px', fontWeight: 'bold', margin: 0 }}>{status.nodes?.total || 0}</p>
                  </div>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Ready</p>
                    <p style={{ fontSize: '24px', fontWeight: 'bold', color: '#10b981', margin: 0 }}>
                      {status.nodes?.ready || 0}
                    </p>
                  </div>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Not Ready</p>
                    <p style={{ fontSize: '24px', fontWeight: 'bold', color: '#ef4444', margin: 0 }}>
                      {status.nodes?.not_ready || 0}
                    </p>
                  </div>
                </div>
              </div>

              {/* Node Roles */}
              <div className="card">
                <h4 style={{ marginBottom: '12px' }}>Node Roles</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Control Plane</p>
                    <p style={{ fontSize: '24px', fontWeight: 'bold', margin: 0 }}>
                      {status.roles?.control_plane || 0}
                    </p>
                  </div>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>ETCD</p>
                    <p style={{ fontSize: '24px', fontWeight: 'bold', margin: 0 }}>
                      {status.roles?.etcd || 0}
                    </p>
                  </div>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Workers</p>
                    <p style={{ fontSize: '24px', fontWeight: 'bold', margin: 0 }}>
                      {status.roles?.worker || 0}
                    </p>
                  </div>
                </div>
              </div>

              {/* CNI */}
              <div className="card">
                <h4 style={{ marginBottom: '12px' }}>CNI Plugin</h4>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Type</p>
                    <p style={{ fontSize: '18px', fontWeight: 'bold', margin: 0, textTransform: 'capitalize' }}>
                      {status.network?.cni?.type || status.cni?.type || 'Unknown'}
                    </p>
                  </div>
                  <div>
                    <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Status</p>
                    <span
                      className={`badge badge-${(status.network?.cni?.status || status.cni?.status) === 'healthy' ? 'success' :
                          (status.network?.cni?.status || status.cni?.status) === 'degraded' ? 'warning' : 'secondary'
                        }`}
                      style={{ fontSize: '14px', textTransform: 'capitalize' }}
                    >
                      {status.network?.cni?.status || status.cni?.status || 'Unknown'}
                    </span>
                  </div>
                  {(status.network?.cni?.pods || status.cni?.pods) && (
                    <div>
                      <p style={{ color: '#64748b', fontSize: '14px', margin: 0 }}>Pods</p>
                      <p style={{ fontSize: '16px', margin: 0 }}>
                        {(status.network?.cni?.pods || status.cni?.pods).running} / {(status.network?.cni?.pods || status.cni?.pods).total} Running
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Components */}
              <div className="card">
                <h4 style={{ marginBottom: '12px' }}>Components</h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
                  {status.components && Object.entries(status.components).map(([name, health]) => (
                    <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ textTransform: 'capitalize', fontSize: '14px' }}>
                        {name.replace('_', ' ')}
                      </span>
                      <span
                        className={`badge badge-${health === 'healthy' ? 'success' :
                            health === 'degraded' ? 'warning' : 'secondary'
                          }`}
                        style={{ textTransform: 'capitalize' }}
                      >
                        {health}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Details Tab */}
      {activeTab === 'details' && (
        <div>
          {!cluster.kubeconfig ? (
            <div className="card" style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
              <p style={{ margin: 0, fontSize: '18px' }}>Configure kubeconfig to view cluster details</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '16px' }}>
              {/* Node Details Table */}
              {(status?.nodes?.details || status?.node_details) && (status?.nodes?.details || status?.node_details).length > 0 && (
                <div className="card">
                  <h4 style={{ marginBottom: '16px' }}>Node Details</h4>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>IP Address</th>
                        <th>Roles</th>
                        <th>Status</th>
                        <th>OS</th>
                        <th>Kernel</th>
                        <th>Version</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(status.nodes?.details || status.node_details).map((node, idx) => (
                        <tr key={idx}>
                          <td><strong>{node.name}</strong></td>
                          <td>{node.internal_ip || node.external_ip || '-'}</td>
                          <td>{node.roles}</td>
                          <td>
                            <span className={`badge badge-${node.status === 'Ready' ? 'success' : 'secondary'}`}>
                              {node.status}
                            </span>
                          </td>
                          <td style={{ fontSize: '13px' }}>{node.os_image || node.os || '-'}</td>
                          <td style={{ fontSize: '13px' }}>{node.kernel || '-'}</td>
                          <td style={{ fontSize: '13px' }}>{node.version || node.kubelet_version || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Namespaces Table */}
              {(status?.workloads?.namespaces_details || status?.namespaces) && (status?.workloads?.namespaces_details || status?.namespaces).length > 0 && (
                <div className="card">
                  <h4 style={{ marginBottom: '16px' }}>Namespaces ({(status?.workloads?.namespaces_details || status?.namespaces).length})</h4>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Status</th>
                        <th>Total Pods</th>
                        <th>Running Pods</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(status.workloads?.namespaces_details || status.namespaces).map((ns, idx) => (
                        <tr key={idx}>
                          <td><strong>{ns.name}</strong></td>
                          <td>
                            <span className="badge badge-success">{ns.status}</span>
                          </td>
                          <td>{ns.total_pods}</td>
                          <td>{ns.running_pods}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* CRDs Table */}
              {(status?.api_compatibility?.crds || status?.crds) && (status?.api_compatibility?.crds || status?.crds).length > 0 && (
                <div className="card">
                  <h4 style={{ marginBottom: '16px' }}>Custom Resource Definitions ({(status?.api_compatibility?.crds || status?.crds).length})</h4>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Kind</th>
                        <th>Group</th>
                        <th>Scope</th>
                        <th>API Versions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(status.api_compatibility?.crds || status.crds).map((crd, idx) => (
                        <tr key={idx}>
                          <td><strong>{crd.name}</strong></td>
                          <td>{crd.kind}</td>
                          <td>{crd.group}</td>
                          <td>{crd.scope}</td>
                          <td>{crd.versions.join(', ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(status?.api_compatibility?.crds || status?.crds) && (status?.api_compatibility?.crds || status?.crds).length === 0 && (
                <div className="card" style={{ textAlign: 'center', padding: '40px 20px', color: '#94a3b8' }}>
                  <p style={{ margin: 0 }}>No Custom Resource Definitions found</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Edit Tab */}
      {activeTab === 'edit' && (
        <div className="card">
          <h3 style={{ marginBottom: '20px' }}>Edit Cluster Metadata</h3>
          <form onSubmit={handleSaveEdit}>
            <div className="form-group">
              <label>Cluster Name</label>
              <input
                type="text"
                value={cluster.name}
                onChange={e => setCluster({ ...cluster, name: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>RKE2 Version</label>
              <input
                type="text"
                value={cluster.rke2_version}
                onChange={e => setCluster({ ...cluster, rke2_version: e.target.value })}
                placeholder="v1.31.1+rke2r1"
              />
            </div>

            <div className="form-group">
              <label>CNI Plugin</label>
              <select
                value={cluster.cni || 'canal'}
                onChange={e => setCluster({ ...cluster, cni: e.target.value })}
              >
                <option value="canal">Canal</option>
                <option value="calico">Calico</option>
                <option value="cilium">Cilium</option>
                <option value="none">None</option>
              </select>
            </div>

            <div className="form-group">
              <label>RKE2 Data Directory</label>
              <input
                type="text"
                value={cluster.rke2_data_dir || '/var/lib/rancher/rke2'}
                onChange={e => setCluster({ ...cluster, rke2_data_dir: e.target.value })}
              />
            </div>

            <div className="form-group">
              <label>RKE2 API IP</label>
              <input
                type="text"
                value={cluster.rke2_api_ip || ''}
                onChange={e => setCluster({ ...cluster, rke2_api_ip: e.target.value })}
                placeholder="10.0.0.1"
              />
            </div>

            <div className="form-group">
              <label>RKE2 Token</label>
              <input
                type="text"
                value={cluster.rke2_token || ''}
                onChange={e => setCluster({ ...cluster, rke2_token: e.target.value })}
              />
            </div>

            <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
              <button type="submit" className="btn btn-primary">
                Save Changes
              </button>
              <button type="button" className="btn btn-secondary" onClick={loadCluster}>
                Reset
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Scale Tab */}
      {activeTab === 'scale' && (
        <div>
          {/* Kubeconfig Required Warning */}
          {!cluster.kubeconfig && (
            <div className="card" style={{ background: '#fef3c7', border: '1px solid #fbbf24', marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ margin: 0, marginBottom: '8px', color: '#92400e' }}>Kubeconfig Required</h4>
                  <p style={{ margin: 0, color: '#92400e' }}>
                    Fetch or upload kubeconfig to view current nodes and enable scaling operations.
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={handleFetchKubeconfig}
                    className="btn btn-primary"
                    disabled={fetchingKubeconfig}
                  >
                    {fetchingKubeconfig ? 'Fetching...' : 'Fetch from Master'}
                  </button>
                  <button onClick={() => setUploadModalOpen(true)} className="btn btn-secondary">
                    Upload Kubeconfig
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Current Nodes Summary */}
          {cluster.kubeconfig && scaleInfo && (
            <div className="card" style={{ marginBottom: '20px' }}>
              <h3 style={{ marginBottom: '16px' }}>Current Nodes</h3>
              <div style={{ display: 'flex', gap: '20px', marginBottom: '20px' }}>
                <div>
                  <span style={{ color: '#64748b' }}>Total:</span>{' '}
                  <strong>{scaleInfo.summary.total}</strong>
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>Servers:</span>{' '}
                  <strong>{scaleInfo.summary.servers}</strong>
                </div>
                <div>
                  <span style={{ color: '#64748b' }}>Agents:</span>{' '}
                  <strong>{scaleInfo.summary.agents}</strong>
                </div>
              </div>

              {/* Node List */}
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: '40px' }}>
                      <input
                        type="checkbox"
                        onChange={e => {
                          if (e.target.checked) {
                            setSelectedNodes(scaleInfo.nodes.map(n => n.hostname))
                          } else {
                            setSelectedNodes([])
                          }
                        }}
                        checked={selectedNodes.length === scaleInfo.nodes.length && scaleInfo.nodes.length > 0}
                      />
                    </th>
                    <th>Hostname</th>
                    <th>Internal IP</th>
                    <th>External IP</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Version</th>
                  </tr>
                </thead>
                <tbody>
                  {scaleInfo.nodes.map((node, idx) => (
                    <tr key={idx}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedNodes.includes(node.hostname)}
                          onChange={e => {
                            if (e.target.checked) {
                              setSelectedNodes([...selectedNodes, node.hostname])
                            } else {
                              setSelectedNodes(selectedNodes.filter(h => h !== node.hostname))
                            }
                          }}
                        />
                      </td>
                      <td><strong>{node.hostname}</strong></td>
                      <td>{node.internal_ip || node.ip || '-'}</td>
                      <td>{node.external_ip || '-'}</td>
                      <td>
                        <span className={`badge badge-${node.role === 'server' ? 'primary' : 'secondary'}`}>
                          {node.role}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-${node.status === 'Ready' ? 'success' : 'warning'}`}>
                          {node.status || 'Unknown'}
                        </span>
                      </td>
                      <td style={{ fontSize: '13px', color: '#64748b' }}>{node.version || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {selectedNodes.length > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <button
                    className="btn btn-danger"
                    onClick={handleRemoveNodes}
                    disabled={scaleLoading}
                  >
                    {scaleLoading ? 'Processing...' : `Remove ${selectedNodes.length} Node(s)`}
                  </button>
                  <span style={{ marginLeft: '12px', color: '#ef4444', fontSize: '14px' }}>
                    ⚠️ This will drain and uninstall RKE2 from selected nodes
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Add New Node */}
          {cluster.kubeconfig && (
            <div className="card">
              <h3 style={{ marginBottom: '20px' }}>Add New Node</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: '12px', alignItems: 'end' }}>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Hostname</label>
                  <input
                    type="text"
                    value={newNodeForm.hostname}
                    onChange={e => setNewNodeForm({ ...newNodeForm, hostname: e.target.value })}
                    placeholder="worker-03"
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Internal IP</label>
                  <input
                    type="text"
                    value={newNodeForm.ip}
                    onChange={e => setNewNodeForm({ ...newNodeForm, ip: e.target.value })}
                    placeholder="10.0.0.5"
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>External IP (Optional)</label>
                  <input
                    type="text"
                    value={newNodeForm.external_ip}
                    onChange={e => setNewNodeForm({ ...newNodeForm, external_ip: e.target.value })}
                    placeholder="203.0.113.10"
                  />
                </div>

                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Role</label>
                  <select
                    value={newNodeForm.role}
                    onChange={e => setNewNodeForm({ ...newNodeForm, role: e.target.value })}
                  >
                    <option value="agent">Agent (Worker)</option>
                    <option value="server">Server (Control Plane)</option>
                  </select>
                </div>

                <div>
                  <button
                    className="btn btn-primary"
                    onClick={handleAddNode}
                    disabled={scaleLoading || !newNodeForm.hostname || !newNodeForm.ip}
                  >
                    {scaleLoading ? 'Adding...' : 'Add Node'}
                  </button>
                </div>
              </div>

              {newNodeForm.external_ip && (
                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <input
                    type="checkbox"
                    id="use-external-ip"
                    checked={newNodeForm.use_external_ip}
                    onChange={e => setNewNodeForm({ ...newNodeForm, use_external_ip: e.target.checked })}
                  />
                  <label htmlFor="use-external-ip" style={{ margin: 0, fontSize: '14px', cursor: 'pointer' }}>
                    Use External IP for SSH connection (Ansible will connect to {newNodeForm.use_external_ip ? newNodeForm.external_ip : newNodeForm.ip})
                  </label>
                </div>
              )}

              <div style={{ marginTop: '16px', padding: '12px', background: '#f1f5f9', borderRadius: '4px' }}>
                <p style={{ margin: 0, fontSize: '14px', color: '#475569' }}>
                  <strong>Note:</strong> Adding a node will execute the Ansible playbook to install RKE2 and join the node to the cluster.
                  The node must be accessible via SSH using the cluster's credential.
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Upgrade Readiness Tab */}
      {activeTab === 'upgrade' && (
        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '20px' }}>
          {/* Left Sidebar - Job History */}
          <div className="card" style={{ maxHeight: '80vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h4 style={{ margin: 0 }}>Check History</h4>
              <button
                onClick={handleNewPreflightCheck}
                className="btn btn-primary"
                style={{ fontSize: '13px', padding: '6px 12px' }}
                disabled={preflightLoading}
              >
                New Check
              </button>
            </div>

            {/* Job Timeline */}
            {upgradeJobs.length === 0 ? (
              <p style={{ color: '#94a3b8', textAlign: 'center', padding: '40px 20px', fontSize: '14px' }}>
                No checks yet. Click "New Check" to start.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {upgradeJobs.map(job => (
                  <div
                    key={job.id}
                    onClick={() => loadJobDetail(job.id)}
                    style={{
                      padding: '12px',
                      background: selectedJob?.id === job.id ? '#dbeafe' : '#f9fafb',
                      border: selectedJob?.id === job.id ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <strong style={{ fontSize: '14px' }}>
                        {job.job_type === 'preflight_check' ? 'Preflight' : 'Upgrade'}
                      </strong>
                      <span className={`badge badge-${
                        job.status === 'success' ? 'success' :
                        job.status === 'running' ? 'warning' :
                        job.status === 'failed' ? 'danger' : 'secondary'
                      }`} style={{ fontSize: '11px' }}>
                        {job.status}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: '#64748b' }}>
                      {new Date(job.created_at).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Panel - Job Details */}
          <div>
            {!selectedJob ? (
              <div className="card" style={{ textAlign: 'center', padding: '60px 20px', color: '#94a3b8' }}>
                <p style={{ margin: 0, fontSize: '18px' }}>Select a check from history to view details</p>
              </div>
            ) : (
              <div className="card">
                {/* Job Header */}
                <div style={{ marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid #e5e7eb' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <h3 style={{ margin: 0, marginBottom: '8px' }}>
                        {selectedJob.job_type === 'preflight_check' ? 'Preflight Check' : 'Upgrade Check'}
                      </h3>
                      <p style={{ margin: 0, color: '#64748b', fontSize: '14px' }}>
                        {new Date(selectedJob.created_at).toLocaleString()}
                      </p>
                      {selectedJob.target_version && (
                        <p style={{ margin: '4px 0 0 0', color: '#3b82f6', fontSize: '14px' }}>
                          Target: <strong>{selectedJob.target_version}</strong>
                        </p>
                      )}
                    </div>
                    <span className={`badge badge-${
                      selectedJob.status === 'success' ? 'success' :
                      selectedJob.status === 'running' ? 'warning' :
                      selectedJob.status === 'failed' ? 'danger' : 'secondary'
                    }`}>
                      {selectedJob.status}
                    </span>
                  </div>
                </div>

                {/* LLM Metrics */}
                {(selectedJob.llm_model || selectedJob.llm_token_count) && (
                  <div style={{
                    marginBottom: '20px',
                    padding: '12px',
                    background: '#f0f9ff',
                    borderRadius: '6px',
                    border: '1px solid #bae6fd'
                  }}>
                    <h5 style={{ margin: 0, marginBottom: '8px', color: '#0369a1' }}>AI Analysis Metrics</h5>
                    <div style={{ display: 'flex', gap: '20px', fontSize: '14px' }}>
                      {selectedJob.llm_model && (
                        <div>
                          <span style={{ color: '#64748b' }}>Model: </span>
                          <strong>{selectedJob.llm_model}</strong>
                        </div>
                      )}
                      {selectedJob.llm_token_count && (
                        <div>
                          <span style={{ color: '#64748b' }}>Tokens: </span>
                          <strong>{selectedJob.llm_token_count.toLocaleString()}</strong>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* AI Analysis Result */}
                {selectedJob.llm_summary && (() => {
                  try {
                    const analysis = JSON.parse(selectedJob.llm_summary)
                    return (
                      <div style={{ marginBottom: '20px' }}>
                        <div style={{
                          padding: '16px',
                          borderRadius: '8px',
                          background: analysis.verdict === 'GO' ? '#d1fae5' :
                            analysis.verdict === 'NO-GO' ? '#fee2e2' : '#fef3c7',
                          border: `2px solid ${analysis.verdict === 'GO' ? '#10b981' :
                            analysis.verdict === 'NO-GO' ? '#ef4444' : '#f59e0b'}`
                        }}>
                          <h4 style={{ margin: 0, marginBottom: '8px', fontSize: '18px' }}>
                            Verdict: <strong>{analysis.verdict}</strong>
                          </h4>
                          <p style={{ margin: 0, color: '#374151' }}>{analysis.reasoning_summary}</p>
                        </div>

                        {analysis.blockers?.length > 0 && (
                          <div style={{ marginTop: '16px' }}>
                            <h5 style={{ color: '#dc2626' }}>🚫 Blockers</h5>
                            <ul style={{ margin: 0, paddingLeft: '20px' }}>
                              {analysis.blockers.map((b, i) => (
                                <li key={i} style={{ color: '#991b1b' }}>{b}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {analysis.risks?.length > 0 && (
                          <div style={{ marginTop: '16px' }}>
                            <h5 style={{ color: '#d97706' }}>⚠️ Risks</h5>
                            <ul style={{ margin: 0, paddingLeft: '20px' }}>
                              {analysis.risks.map((r, i) => (
                                <li key={i} style={{ color: '#92400e' }}>{r}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {analysis.action_plan?.length > 0 && (
                          <div style={{ marginTop: '16px' }}>
                            <h5 style={{ color: '#2563eb' }}>📋 Action Plan</h5>
                            <ol style={{ margin: 0, paddingLeft: '20px' }}>
                              {analysis.action_plan.map((step, i) => (
                                <li key={i} style={{ color: '#1e40af', marginBottom: '4px' }}>{step}</li>
                              ))}
                            </ol>
                          </div>
                        )}
                      </div>
                    )
                  } catch (e) {
                    return (
                      <div style={{ padding: '12px', background: '#fee2e2', borderRadius: '4px', marginBottom: '20px' }}>
                        <strong>Failed to parse AI analysis</strong>
                      </div>
                    )
                  }
                })()}

                {/* Raw Check Results */}
                {selectedJob.readiness_json?.checks && (
                  <div>
                    <h4>Check Results ({selectedJob.readiness_json.checks.length})</h4>
                    {selectedJob.readiness_json.checks.map((check, i) => (
                      <div
                        key={i}
                        style={{
                          padding: '12px',
                          marginBottom: '8px',
                          borderLeft: `4px solid ${check.severity === 'CRITICAL' ? '#ef4444' :
                            check.severity === 'WARN' ? '#f59e0b' : '#10b981'}`,
                          background: '#f9fafb',
                          borderRadius: '4px'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <strong>{check.message}</strong>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: '12px',
                            fontSize: '12px',
                            background: check.severity === 'CRITICAL' ? '#fee2e2' :
                              check.severity === 'WARN' ? '#fef3c7' : '#d1fae5',
                            color: check.severity === 'CRITICAL' ? '#991b1b' :
                              check.severity === 'WARN' ? '#92400e' : '#065f46'
                          }}>
                            {check.severity}
                          </span>
                        </div>
                        <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                          {check.category} • {check.node_name || 'cluster-wide'}
                        </div>
                      </div>
                    ))}

                    {selectedJob.readiness_json.checks.length === 0 && (
                      <p style={{ color: '#10b981', textAlign: 'center', padding: '20px' }}>
                        ✅ All checks passed! No issues detected.
                      </p>
                    )}
                  </div>
                )}

                {/* Running Status */}
                {selectedJob.status === 'running' && (
                  <div style={{ textAlign: 'center', padding: '20px', color: '#f59e0b' }}>
                    <p>⏳ Check is running... Results will appear here.</p>
                  </div>
                )}

                {/* Failed Status */}
                {selectedJob.status === 'failed' && (
                  <div style={{ padding: '12px', background: '#fee2e2', borderRadius: '4px', marginTop: '20px' }}>
                    <strong>Check Failed:</strong>
                    <pre style={{ marginTop: '8px', fontSize: '12px', whiteSpace: 'pre-wrap' }}>{selectedJob.output}</pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Upload Kubeconfig Modal */}
      {uploadModalOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'white',
            padding: '30px',
            borderRadius: '8px',
            maxWidth: '600px',
            width: '100%'
          }}>
            <h3 style={{ marginBottom: '20px' }}>Upload Kubeconfig</h3>
            <p style={{ marginBottom: '12px', color: '#64748b' }}>
              Paste your kubeconfig content below:
            </p>
            <textarea
              value={kubeconfigContent}
              onChange={e => setKubeconfigContent(e.target.value)}
              placeholder="Paste kubeconfig YAML content here..."
              style={{
                width: '100%',
                minHeight: '200px',
                padding: '12px',
                border: '1px solid #e2e8f0',
                borderRadius: '4px',
                fontFamily: 'monospace',
                fontSize: '13px',
                marginBottom: '20px'
              }}
            />
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setUploadModalOpen(false)
                  setKubeconfigContent('')
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleUploadKubeconfig}
                disabled={!kubeconfigContent.trim()}
              >
                Upload
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Alert Modal */}
      <AlertModal
        isOpen={alertModal.isOpen}
        onClose={() => setAlertModal({ ...alertModal, isOpen: false })}
        title={alertModal.title}
        message={alertModal.message}
        type={alertModal.type}
      />

      {/* Confirm Modal */}
      <ConfirmModal
        isOpen={confirmModal.isOpen}
        onClose={() => setConfirmModal({ ...confirmModal, isOpen: false })}
        onConfirm={confirmModal.onConfirm}
        title={confirmModal.title}
        message={confirmModal.message}
        type={confirmModal.type}
        confirmText={confirmModal.confirmText}
      />

      {/* AI Selection Modal for New Check */}
      {aiSelectionModalOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000
        }}>
          <div style={{
            background: 'white',
            borderRadius: '8px',
            padding: '24px',
            maxWidth: '500px',
            width: '90%'
          }}>
            <h3 style={{ margin: 0, marginBottom: '16px' }}>Start Preflight Check</h3>

            {/* Target Version Input */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold', fontSize: '14px' }}>
                Target RKE2 Version (Optional)
              </label>
              <input
                type="text"
                value={targetVersion}
                onChange={(e) => setTargetVersion(e.target.value)}
                placeholder="e.g., v1.30.2+rke2r1"
                style={{
                  width: '100%',
                  padding: '10px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              />
              <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#64748b' }}>
                Specify target version for compatibility analysis. Leave empty for general health check.
              </p>
            </div>

            {/* AI Analysis Checkbox */}
            <div style={{ marginBottom: '20px', padding: '16px', background: '#f1f5f9', borderRadius: '6px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '16px' }}>
                <input
                  type="checkbox"
                  checked={useAiAnalysis}
                  onChange={(e) => setUseAiAnalysis(e.target.checked)}
                  style={{ width: '18px', height: '18px' }}
                />
                <span><strong>Enable AI Analysis</strong> (DeepSeek R1 via AWS Bedrock)</span>
              </label>
              <p style={{ margin: '8px 0 0 26px', fontSize: '13px', color: '#64748b' }}>
                AI provides: verdict (GO/NO-GO/CAUTION), blockers, risks, and action plan. Token costs apply.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button onClick={() => setAiSelectionModalOpen(false)} className="btn btn-secondary">
                Cancel
              </button>
              <button onClick={handleConfirmPreflightCheck} className="btn btn-primary" disabled={preflightLoading}>
                {preflightLoading ? 'Starting...' : 'Start Check'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
