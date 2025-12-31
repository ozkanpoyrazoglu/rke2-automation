import { useState, useEffect } from 'react'
import { listClusters, deleteCluster, installCluster, checkUpgradeReadiness } from '../api'
import { useNavigate } from 'react-router-dom'
import { AlertModal, ConfirmModal, ConfirmWithTextModal } from '../components/Modal'

export default function Clusters() {
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)
  const [uninstallModal, setUninstallModal] = useState(null)
  const navigate = useNavigate()

  // Modal states
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info' })
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null, type: 'warning' })

  const loadClusters = () => {
    listClusters()
      .then(res => setClusters(res.data))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadClusters()
  }, [])

  const handleInstall = (clusterId) => {
    setConfirmModal({
      isOpen: true,
      title: 'Start Installation',
      message: 'Start RKE2 installation for this cluster?',
      type: 'info',
      confirmText: 'Start Installation',
      onConfirm: () => {
        installCluster(clusterId)
          .then(res => {
            setAlertModal({
              isOpen: true,
              title: 'Job Started',
              message: 'Installation job started',
              type: 'success'
            })
            setTimeout(() => navigate(`/jobs/${res.data.id}`), 1500)
          })
          .catch(err => {
            setAlertModal({
              isOpen: true,
              title: 'Error',
              message: err.response?.data?.detail || err.message,
              type: 'error'
            })
          })
      }
    })
  }

  const handleUpgradeCheck = (clusterId) => {
    checkUpgradeReadiness(clusterId)
      .then(res => {
        setAlertModal({
          isOpen: true,
          title: 'Check Started',
          message: 'Upgrade readiness check started',
          type: 'success'
        })
        setTimeout(() => navigate(`/jobs/${res.data.id}`), 1500)
      })
      .catch(err => {
        setAlertModal({
          isOpen: true,
          title: 'Error',
          message: err.response?.data?.detail || err.message,
          type: 'error'
        })
      })
  }

  const handleUninstall = (cluster) => {
    setUninstallModal(cluster)
  }

  const executeUninstall = () => {
    fetch(`http://localhost:8000/api/jobs/uninstall/${uninstallModal.id}?confirmation=${encodeURIComponent(uninstallModal.name)}`, {
      method: 'POST'
    })
      .then(async res => {
        const data = await res.json()
        if (!res.ok) {
          // Handle error responses (400, 409, 500, etc.)
          throw new Error(data.detail || `Server error: ${res.status}`)
        }
        return data
      })
      .then(job => {
        setAlertModal({
          isOpen: true,
          title: 'Job Started',
          message: 'Uninstall job started',
          type: 'success'
        })
        setUninstallModal(null)
        setTimeout(() => navigate(`/jobs/${job.id}`), 1500)
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

  const handleDelete = (clusterId, clusterName) => {
    setConfirmModal({
      isOpen: true,
      title: 'Delete Cluster',
      message: `Delete cluster "${clusterName}"?\n\nThis only removes from database, not from nodes.`,
      type: 'danger',
      confirmText: 'Delete',
      onConfirm: () => {
        deleteCluster(clusterId)
          .then(() => {
            setAlertModal({
              isOpen: true,
              title: 'Success',
              message: 'Cluster deleted',
              type: 'success'
            })
            loadClusters()
          })
          .catch(err => {
            setAlertModal({
              isOpen: true,
              title: 'Error',
              message: err.response?.data?.detail || err.message,
              type: 'error'
            })
          })
      }
    })
  }

  if (loading) return <div className="loading">Loading...</div>

  return (
    <div>
      <div className="page-header">
        <h2>Clusters</h2>
        <p>Manage RKE2 clusters</p>
      </div>

      <div className="card">
        {clusters.length === 0 ? (
          <p style={{ color: '#64748b' }}>No clusters yet. Create one to get started.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>RKE2 Version</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {clusters.map(cluster => (
                <tr key={cluster.id}>
                  <td>
                    <strong
                      onClick={() => navigate(`/clusters/${cluster.id}`)}
                      style={{ cursor: 'pointer', color: '#3b82f6', textDecoration: 'underline' }}
                    >
                      {cluster.name}
                    </strong>
                  </td>
                  <td>
                    <span className={`badge badge-${cluster.cluster_type === 'new' ? 'info' : 'success'}`}>
                      {cluster.cluster_type}
                    </span>
                  </td>
                  <td>{cluster.rke2_version}</td>
                  <td>{new Date(cluster.created_at).toLocaleDateString()}</td>
                  <td>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      {cluster.cluster_type === 'new' && (
                        <>
                          <button
                            className="btn btn-primary"
                            style={{ padding: '6px 12px', fontSize: '12px' }}
                            onClick={() => handleInstall(cluster.id)}
                          >
                            Install
                          </button>
                          <button
                            className="btn"
                            style={{ padding: '6px 12px', fontSize: '12px', background: '#f59e0b', color: 'white' }}
                            onClick={() => handleUninstall(cluster)}
                          >
                            Uninstall RKE2
                          </button>
                        </>
                      )}
                      {cluster.cluster_type === 'registered' && (
                        <button
                          className="btn btn-primary"
                          style={{ padding: '6px 12px', fontSize: '12px' }}
                          onClick={() => handleUpgradeCheck(cluster.id)}
                        >
                          Check Upgrade
                        </button>
                      )}
                      <button
                        className="btn btn-danger"
                        style={{ padding: '6px 12px', fontSize: '12px' }}
                        onClick={() => handleDelete(cluster.id, cluster.name)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Uninstall Confirmation Modal */}
      <ConfirmWithTextModal
        isOpen={!!uninstallModal}
        onClose={() => setUninstallModal(null)}
        onConfirm={executeUninstall}
        title="⚠️ Uninstall RKE2 Cluster"
        message={`This will run /usr/local/bin/rke2-uninstall.sh on all nodes and remove:

• RKE2 installation
• All container images
• Kubernetes data and configuration
• etcd data

This action cannot be undone!`}
        confirmationText={uninstallModal?.name || ''}
        placeholder={`Type "${uninstallModal?.name}" here`}
      />

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
    </div>
  )
}
