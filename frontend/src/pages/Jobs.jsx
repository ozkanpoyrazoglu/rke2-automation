import { useState, useEffect } from 'react'
import { listJobs } from '../api'
import { Link } from 'react-router-dom'

export default function Jobs() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listJobs()
      .then(res => setJobs(res.data))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="loading">Loading...</div>

  return (
    <div>
      <div className="page-header">
        <h2>Jobs</h2>
        <p>Ansible execution history</p>
      </div>

      <div className="card">
        {jobs.length === 0 ? (
          <p style={{ color: '#64748b' }}>No jobs yet</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Cluster ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Created</th>
                <th>Duration</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td>{job.cluster_id}</td>
                  <td>{job.job_type}</td>
                  <td>
                    <span className={`badge badge-${getStatusColor(job.status)}`}>
                      {job.status}
                    </span>
                  </td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>{getDuration(job)}</td>
                  <td>
                    <Link
                      to={`/jobs/${job.id}`}
                      className="btn btn-secondary"
                      style={{ padding: '6px 12px', fontSize: '12px' }}
                    >
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

function getDuration(job) {
  if (!job.started_at) return '-'

  const start = new Date(job.started_at)
  const end = job.completed_at ? new Date(job.completed_at) : new Date()
  const seconds = Math.floor((end - start) / 1000)

  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}
