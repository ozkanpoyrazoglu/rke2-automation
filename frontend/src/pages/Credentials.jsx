import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Credentials() {
  const navigate = useNavigate()
  const [credentials, setCredentials] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    username: '',
    credential_type: 'ssh_key',
    secret: ''
  })

  const loadCredentials = () => {
    fetch('http://localhost:8000/api/credentials')
      .then(res => res.json())
      .then(data => setCredentials(data))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadCredentials()
  }, [])

  const handleSubmit = (e) => {
    e.preventDefault()

    fetch('http://localhost:8000/api/credentials', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
      .then(res => {
        if (!res.ok) throw new Error('Failed to create credential')
        return res.json()
      })
      .then(() => {
        alert('Credential created successfully')
        setShowForm(false)
        setFormData({ name: '', username: '', credential_type: 'ssh_key', secret: '' })
        loadCredentials()
      })
      .catch(err => alert(`Error: ${err.message}`))
  }

  const handleDelete = (id, name) => {
    if (confirm(`Delete credential "${name}"?`)) {
      fetch(`http://localhost:8000/api/credentials/${id}`, { method: 'DELETE' })
        .then(() => {
          alert('Credential deleted')
          loadCredentials()
        })
        .catch(err => alert(`Error: ${err.message}`))
    }
  }

  if (loading) return <div className="loading">Loading...</div>

  return (
    <div>
      <div className="page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2>SSH Credentials</h2>
            <p>Manage SSH keys and passwords for cluster access</p>
          </div>
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancel' : '+ New Credential'}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: '20px' }}>
          <h3 style={{ marginBottom: '20px' }}>New Credential</h3>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Name</label>
              <input
                type="text"
                placeholder="production-ssh-key"
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>Username</label>
              <input
                type="text"
                placeholder="ubuntu"
                value={formData.username}
                onChange={e => setFormData({ ...formData, username: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>Type</label>
              <select
                value={formData.credential_type}
                onChange={e => setFormData({ ...formData, credential_type: e.target.value })}
              >
                <option value="ssh_key">SSH Private Key</option>
                <option value="ssh_password">SSH Password (not recommended)</option>
              </select>
            </div>

            <div className="form-group">
              <label>{formData.credential_type === 'ssh_key' ? 'Private Key' : 'Password'}</label>
              <textarea
                rows={formData.credential_type === 'ssh_key' ? 12 : 2}
                placeholder={
                  formData.credential_type === 'ssh_key'
                    ? '-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----'
                    : 'Enter password'
                }
                value={formData.secret}
                onChange={e => setFormData({ ...formData, secret: e.target.value })}
                required
                style={{ fontFamily: 'monospace', fontSize: '12px' }}
              />
              <small style={{ color: '#64748b', marginTop: '8px', display: 'block' }}>
                {formData.credential_type === 'ssh_key'
                  ? 'Paste your private key content. It will be encrypted before storage.'
                  : 'Password will be encrypted before storage. SSH keys are recommended for better security.'}
              </small>
            </div>

            <button type="submit" className="btn btn-primary">
              Create Credential
            </button>
          </form>
        </div>
      )}

      <div className="card">
        {credentials.length === 0 ? (
          <p style={{ color: '#64748b' }}>No credentials yet. Create one to get started.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Username</th>
                <th>Type</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {credentials.map(cred => (
                <tr key={cred.id}>
                  <td><strong>{cred.name}</strong></td>
                  <td>{cred.username}</td>
                  <td>
                    <span className={`badge badge-${cred.credential_type === 'ssh_key' ? 'success' : 'warning'}`}>
                      {cred.credential_type === 'ssh_key' ? 'SSH Key' : 'Password'}
                    </span>
                  </td>
                  <td>{new Date(cred.created_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      className="btn btn-danger"
                      style={{ padding: '6px 12px', fontSize: '12px' }}
                      onClick={() => handleDelete(cred.id, cred.name)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
