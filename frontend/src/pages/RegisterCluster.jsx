import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { registerCluster } from '../api'

export default function RegisterCluster() {
  const navigate = useNavigate()
  const [formData, setFormData] = useState({
    name: '',
    target_rke2_version: 'v1.28.5+rke2r1',
    kubeconfig: ''
  })

  const handleSubmit = (e) => {
    e.preventDefault()

    registerCluster(formData)
      .then(() => {
        alert('Cluster registered successfully')
        navigate('/clusters')
      })
      .catch(err => {
        alert(`Error: ${err.response?.data?.detail || err.message}`)
      })
  }

  return (
    <div>
      <div className="page-header">
        <h2>Register Cluster</h2>
        <p>Register an existing RKE2 cluster for upgrade readiness checks</p>
      </div>

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Cluster Name</label>
            <input
              type="text"
              placeholder="production-cluster"
              value={formData.name}
              onChange={e => setFormData({ ...formData, name: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label>Target RKE2 Version (for upgrade planning)</label>
            <input
              type="text"
              placeholder="v1.28.5+rke2r1"
              value={formData.target_rke2_version}
              onChange={e => setFormData({ ...formData, target_rke2_version: e.target.value })}
              required
            />
          </div>

          <div className="form-group">
            <label>Kubeconfig</label>
            <textarea
              rows={12}
              placeholder="Paste your kubeconfig file contents here..."
              value={formData.kubeconfig}
              onChange={e => setFormData({ ...formData, kubeconfig: e.target.value })}
              required
              style={{ fontFamily: 'monospace', fontSize: '12px' }}
            />
            <small style={{ color: '#64748b', marginTop: '8px', display: 'block' }}>
              The kubeconfig will be stored securely and used only for cluster analysis
            </small>
          </div>

          <div style={{ display: 'flex', gap: '12px' }}>
            <button type="submit" className="btn btn-primary">
              Register Cluster
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate('/clusters')}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
