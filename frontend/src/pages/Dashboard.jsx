import { useState, useEffect } from 'react'
import { listClusters, listJobs } from '../api'
import { Link } from 'react-router-dom'

export default function Dashboard() {
  const [stats, setStats] = useState({
    totalClusters: 0,
    newClusters: 0,
    registeredClusters: 0,
    recentJobs: []
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([listClusters(), listJobs()])
      .then(([clustersRes, jobsRes]) => {
        const clusters = clustersRes.data
        const jobs = jobsRes.data.slice(0, 5)

        setStats({
          totalClusters: clusters.length,
          newClusters: clusters.filter(c => c.cluster_type === 'new').length,
          registeredClusters: clusters.filter(c => c.cluster_type === 'registered').length,
          recentJobs: jobs
        })
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading">Loading...</div>

  return (
    <div>
      <div className="page-header">
        <h2>Dashboard</h2>
        <p>RKE2 cluster management overview</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px', marginBottom: '30px' }}>
        <div className="card">
          <h3 style={{ fontSize: '14px', color: '#64748b', marginBottom: '8px' }}>Total Clusters</h3>
          <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#1e293b' }}>{stats.totalClusters}</div>
        </div>
        <div className="card">
          <h3 style={{ fontSize: '14px', color: '#64748b', marginBottom: '8px' }}>New Clusters</h3>
          <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#3b82f6' }}>{stats.newClusters}</div>
        </div>
        <div className="card">
          <h3 style={{ fontSize: '14px', color: '#64748b', marginBottom: '8px' }}>Registered Clusters</h3>
          <div style={{ fontSize: '32px', fontWeight: 'bold', color: '#10b981' }}>{stats.registeredClusters}</div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: '20px', fontSize: '18px' }}>Recent Jobs</h3>
        {stats.recentJobs.length === 0 ? (
          <p style={{ color: '#64748b' }}>No jobs yet</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {stats.recentJobs.map(job => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.job_type}</td>
                  <td>
                    <span className={`badge badge-${getStatusColor(job.status)}`}>
                      {job.status}
                    </span>
                  </td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>
                    <Link to={`/jobs/${job.id}`} className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }}>
                      View
                    </Link>
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

function getStatusColor(status) {
  switch (status) {
    case 'success': return 'success'
    case 'failed': return 'danger'
    case 'running': return 'info'
    default: return 'warning'
  }
}
