import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { createNewCluster } from '../api'

export default function NewCluster() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [credentials, setCredentials] = useState([])
  const [testingAccess, setTestingAccess] = useState(false)
  const [accessResults, setAccessResults] = useState(null)
  const [formData, setFormData] = useState({
    name: '',
    rke2_version: 'v1.28.5+rke2r1',
    credential_id: '',
    registry_mode: 'internet',
    custom_registry_url: '',
    custom_config: '',
    cni: 'canal',
    nodes: [
      { hostname: '', ip: '', role: 'server' }
    ],
    // Custom images (optional)
    kube_apiserver_image: '',
    kube_controller_manager_image: '',
    kube_proxy_image: '',
    kube_scheduler_image: '',
    pause_image: '',
    runtime_image: '',
    etcd_image: ''
  })
  const [showAdvanced, setShowAdvanced] = useState(false)

  useEffect(() => {
    // Load credentials
    fetch('http://localhost:8000/api/credentials')
      .then(res => res.json())
      .then(data => {
        setCredentials(data)
        if (data.length > 0) {
          setFormData(prev => ({ ...prev, credential_id: data[0].id }))
        }
      })
      .catch(err => console.error('Failed to load credentials:', err))
  }, [])

  const addNode = () => {
    setFormData({
      ...formData,
      nodes: [...formData.nodes, { hostname: '', ip: '', role: 'agent' }]
    })
  }

  const updateNode = (index, field, value) => {
    const newNodes = [...formData.nodes]
    newNodes[index][field] = value
    setFormData({ ...formData, nodes: newNodes })
  }

  const removeNode = (index) => {
    setFormData({
      ...formData,
      nodes: formData.nodes.filter((_, i) => i !== index)
    })
  }

  const handleTestAccess = () => {
    setTestingAccess(true)
    setAccessResults(null)

    const hosts = formData.nodes.map(node => ({
      hostname: node.hostname,
      ip: node.ip
    }))

    fetch('http://localhost:8000/api/credentials/test-access', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        credential_id: formData.credential_id,
        hosts: hosts
      })
    })
      .then(res => res.json())
      .then(data => {
        setAccessResults(data)
      })
      .catch(err => {
        alert(`Access check failed: ${err.message}`)
      })
      .finally(() => {
        setTestingAccess(false)
      })
  }

  const handleSubmit = () => {
    // Clean up empty string values for optional image fields
    const cleanedData = { ...formData }
    const imageFields = [
      'kube_apiserver_image', 'kube_controller_manager_image',
      'kube_proxy_image', 'kube_scheduler_image',
      'pause_image', 'runtime_image', 'etcd_image'
    ]
    imageFields.forEach(field => {
      if (!cleanedData[field]) {
        cleanedData[field] = null
      }
    })

    createNewCluster(cleanedData)
      .then(() => {
        alert('Cluster created successfully')
        navigate('/clusters')
      })
      .catch(err => {
        alert(`Error: ${err.response?.data?.detail || err.message}`)
      })
  }

  return (
    <div>
      <div className="page-header">
        <h2>New Cluster</h2>
        <p>Create a new RKE2 cluster</p>
      </div>

      {/* Step 1: Basic Info */}
      {step === 1 && (
        <div className="card">
          <h3 style={{ marginBottom: '20px' }}>Step 1: Basic Configuration</h3>

          <div className="form-group">
            <label>Cluster Name</label>
            <input
              type="text"
              placeholder="production-cluster"
              value={formData.name}
              onChange={e => setFormData({ ...formData, name: e.target.value })}
            />
          </div>

          <div className="form-group">
            <label>RKE2 Version</label>
            <input
              type="text"
              placeholder="v1.28.5+rke2r1"
              value={formData.rke2_version}
              onChange={e => setFormData({ ...formData, rke2_version: e.target.value })}
            />
          </div>

          <div className="form-group">
            <label>SSH Credential</label>
            <select
              value={formData.credential_id}
              onChange={e => setFormData({ ...formData, credential_id: parseInt(e.target.value) })}
              required
            >
              {credentials.length === 0 ? (
                <option value="">No credentials available</option>
              ) : (
                credentials.map(cred => (
                  <option key={cred.id} value={cred.id}>
                    {cred.name} ({cred.username})
                  </option>
                ))
              )}
            </select>
            {credentials.length === 0 && (
              <small style={{ color: '#ef4444', marginTop: '8px', display: 'block' }}>
                Please create a credential first in the Credentials page
              </small>
            )}
          </div>

          <div className="form-group">
            <label>CNI Plugin</label>
            <select
              value={formData.cni}
              onChange={e => setFormData({ ...formData, cni: e.target.value })}
            >
              <option value="canal">Canal (default)</option>
              <option value="calico">Calico</option>
              <option value="cilium">Cilium</option>
              <option value="none">None (bring your own)</option>
            </select>
            <small style={{ color: '#64748b', marginTop: '4px', display: 'block' }}>
              Container Network Interface plugin for pod networking
            </small>
          </div>

          <div className="form-group">
            <label>Registry Mode</label>
            <select
              value={formData.registry_mode}
              onChange={e => setFormData({ ...formData, registry_mode: e.target.value })}
            >
              <option value="internet">Internet-connected</option>
              <option value="airgap">Air-gapped</option>
              <option value="custom">Custom Registry</option>
            </select>
          </div>

          {formData.registry_mode === 'custom' && (
            <div className="form-group">
              <label>Custom Registry URL</label>
              <input
                type="text"
                placeholder="registry.example.com"
                value={formData.custom_registry_url}
                onChange={e => setFormData({ ...formData, custom_registry_url: e.target.value })}
              />
            </div>
          )}

          {/* Advanced Settings */}
          <div style={{ marginTop: '30px', paddingTop: '20px', borderTop: '1px solid #e2e8f0' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{ marginBottom: '16px' }}
            >
              {showAdvanced ? '▼' : '▶'} Advanced Settings (Custom Container Images)
            </button>

            {showAdvanced && (
              <div style={{ background: '#f8fafc', padding: '16px', borderRadius: '6px' }}>
                <p style={{ fontSize: '14px', color: '#64748b', marginBottom: '16px' }}>
                  Override default container images (optional). Leave empty to use RKE2 defaults.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div className="form-group">
                    <label>API Server Image</label>
                    <input
                      type="text"
                      placeholder="public.ecr.aws/eks-distro/kubernetes/kube-apiserver:v1.30.14-eks-1-30-49"
                      value={formData.kube_apiserver_image}
                      onChange={e => setFormData({ ...formData, kube_apiserver_image: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Controller Manager Image</label>
                    <input
                      type="text"
                      placeholder="public.ecr.aws/eks-distro/kubernetes/kube-controller-manager:..."
                      value={formData.kube_controller_manager_image}
                      onChange={e => setFormData({ ...formData, kube_controller_manager_image: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Kube Proxy Image</label>
                    <input
                      type="text"
                      placeholder="public.ecr.aws/eks-distro/kubernetes/kube-proxy:..."
                      value={formData.kube_proxy_image}
                      onChange={e => setFormData({ ...formData, kube_proxy_image: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Scheduler Image</label>
                    <input
                      type="text"
                      placeholder="public.ecr.aws/eks-distro/kubernetes/kube-scheduler:..."
                      value={formData.kube_scheduler_image}
                      onChange={e => setFormData({ ...formData, kube_scheduler_image: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Pause Image</label>
                    <input
                      type="text"
                      placeholder="public.ecr.aws/eks-distro/kubernetes/pause:..."
                      value={formData.pause_image}
                      onChange={e => setFormData({ ...formData, pause_image: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Runtime Image</label>
                    <input
                      type="text"
                      placeholder="rancher/rke2-runtime:..."
                      value={formData.runtime_image}
                      onChange={e => setFormData({ ...formData, runtime_image: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label>Etcd Image</label>
                    <input
                      type="text"
                      placeholder="public.ecr.aws/eks-distro/etcd-io/etcd:..."
                      value={formData.etcd_image}
                      onChange={e => setFormData({ ...formData, etcd_image: e.target.value })}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <button className="btn btn-primary" onClick={() => setStep(2)} style={{ marginTop: '20px' }}>
            Next: Add Nodes
          </button>
        </div>
      )}

      {/* Step 2: Nodes */}
      {step === 2 && (
        <div className="card">
          <h3 style={{ marginBottom: '20px' }}>Step 2: Add Nodes</h3>

          {formData.nodes.map((node, idx) => (
            <div key={idx} style={{ border: '1px solid #e2e8f0', padding: '16px', borderRadius: '6px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                <strong>Node {idx + 1}</strong>
                {formData.nodes.length > 1 && (
                  <button
                    className="btn btn-danger"
                    style={{ padding: '4px 8px', fontSize: '12px' }}
                    onClick={() => removeNode(idx)}
                  >
                    Remove
                  </button>
                )}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                <div className="form-group">
                  <label>Hostname</label>
                  <input
                    type="text"
                    placeholder="node-1"
                    value={node.hostname}
                    onChange={e => updateNode(idx, 'hostname', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>IP Address</label>
                  <input
                    type="text"
                    placeholder="192.168.1.10"
                    value={node.ip}
                    onChange={e => updateNode(idx, 'ip', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label>Role</label>
                  <select value={node.role} onChange={e => updateNode(idx, 'role', e.target.value)}>
                    <option value="server">Server (Master)</option>
                    <option value="agent">Agent (Worker)</option>
                  </select>
                </div>
              </div>
            </div>
          ))}

          <button className="btn btn-secondary" onClick={addNode} style={{ marginBottom: '20px' }}>
            + Add Node
          </button>

          {/* Test Access Section */}
          <div style={{ marginTop: '20px', marginBottom: '20px', padding: '16px', background: '#f8fafc', borderRadius: '6px' }}>
            <h4 style={{ fontSize: '14px', marginBottom: '12px' }}>Pre-flight Access Check (Recommended)</h4>
            <button
              className="btn btn-primary"
              onClick={handleTestAccess}
              disabled={testingAccess || formData.nodes.some(n => !n.hostname || !n.ip)}
              style={{ marginBottom: '12px' }}
            >
              {testingAccess ? 'Testing Access...' : 'Test SSH Access'}
            </button>

            {accessResults && (
              <div style={{ marginTop: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <span className={`badge badge-${accessResults.overall_status === 'success' ? 'success' : 'danger'}`}>
                    {accessResults.overall_status === 'success' ? 'ALL CHECKS PASSED' : 'SOME CHECKS FAILED'}
                  </span>
                </div>

                <table className="table">
                  <thead>
                    <tr>
                      <th>Host</th>
                      <th>SSH</th>
                      <th>Sudo</th>
                      <th>OS</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accessResults.results.map((result, idx) => (
                      <tr key={idx}>
                        <td><strong>{result.hostname}</strong><br/><small style={{color: '#64748b'}}>{result.ip}</small></td>
                        <td>
                          <span className={`badge badge-${result.ssh_reachable ? 'success' : 'danger'}`}>
                            {result.ssh_reachable ? '✓' : '✗'}
                          </span>
                        </td>
                        <td>
                          <span className={`badge badge-${result.sudo_available ? 'success' : 'danger'}`}>
                            {result.sudo_available ? '✓' : '✗'}
                          </span>
                        </td>
                        <td>
                          <span className={`badge badge-${result.os_compatible ? 'success' : 'danger'}`}>
                            {result.os_compatible ? '✓' : '✗'}
                          </span>
                        </td>
                        <td>
                          {result.error ? (
                            <small style={{ color: '#ef4444' }}>{result.error}</small>
                          ) : (
                            <span className="badge badge-success">OK</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button className="btn btn-secondary" onClick={() => setStep(1)}>
              Back
            </button>
            <button className="btn btn-primary" onClick={() => setStep(3)}>
              Next: Review
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Review */}
      {step === 3 && (
        <div className="card">
          <h3 style={{ marginBottom: '20px' }}>Step 3: Review and Create</h3>

          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '14px', color: '#64748b', marginBottom: '8px' }}>Cluster Name</h4>
            <p style={{ fontSize: '16px', fontWeight: 'bold' }}>{formData.name}</p>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '14px', color: '#64748b', marginBottom: '8px' }}>RKE2 Version</h4>
            <p>{formData.rke2_version}</p>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '14px', color: '#64748b', marginBottom: '8px' }}>Registry Mode</h4>
            <p>{formData.registry_mode}</p>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '14px', color: '#64748b', marginBottom: '8px' }}>Nodes</h4>
            <table className="table">
              <thead>
                <tr>
                  <th>Hostname</th>
                  <th>IP</th>
                  <th>Role</th>
                </tr>
              </thead>
              <tbody>
                {formData.nodes.map((node, idx) => (
                  <tr key={idx}>
                    <td>{node.hostname}</td>
                    <td>{node.ip}</td>
                    <td>
                      <span className={`badge badge-${node.role === 'server' ? 'info' : 'success'}`}>
                        {node.role === 'server' ? 'Master' : 'Worker'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button className="btn btn-secondary" onClick={() => setStep(2)}>
              Back
            </button>
            <button className="btn btn-primary" onClick={handleSubmit}>
              Create Cluster
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
