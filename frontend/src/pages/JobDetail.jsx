import { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { getJob } from '../api'

export default function JobDetail() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [liveOutput, setLiveOutput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const outputRef = useRef(null)
  const eventSourceRef = useRef(null)

  useEffect(() => {
    const loadJob = () => {
      getJob(jobId)
        .then(res => {
          setJob(res.data)

          // Start streaming if job is running and not already streaming
          if (res.data.status === 'running' && !isStreaming) {
            startStreaming()
          }
        })
        .finally(() => setLoading(false))
    }

    loadJob()

    // Poll for updates
    const interval = setInterval(() => {
      loadJob()
    }, 3000)

    return () => {
      clearInterval(interval)
      stopStreaming()
    }
  }, [jobId])

  const startStreaming = () => {
    if (eventSourceRef.current) return

    setIsStreaming(true)
    const eventSource = new EventSource(`http://localhost:8000/api/jobs/${jobId}/stream`)
    eventSourceRef.current = eventSource

    eventSource.onmessage = (event) => {
      setLiveOutput(prev => prev + event.data)

      // Auto-scroll to bottom
      if (outputRef.current) {
        outputRef.current.scrollTop = outputRef.current.scrollHeight
      }
    }

    eventSource.onerror = () => {
      stopStreaming()
    }
  }

  const stopStreaming = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsStreaming(false)
  }

  const handleTerminate = () => {
    if (!confirm('Are you sure you want to terminate this job?')) return

    fetch(`http://localhost:8000/api/jobs/${jobId}/terminate`, {
      method: 'POST'
    })
      .then(res => res.json())
      .then(() => {
        alert('Job terminated successfully')
        window.location.reload()
      })
      .catch(err => {
        alert(`Failed to terminate job: ${err.message}`)
      })
  }

  if (loading) return <div className="loading">Loading...</div>
  if (!job) return <div className="loading">Job not found</div>

  return (
    <div>
      <div className="page-header">
        <h2>Job #{job.id}</h2>
        <p>{job.job_type} - Cluster ID {job.cluster_id}</p>
      </div>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px', flex: 1 }}>
            <div>
              <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>Status</div>
              <span className={`badge badge-${getStatusColor(job.status)}`}>
                {job.status}
              </span>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>Started</div>
              <div>{job.started_at ? new Date(job.started_at).toLocaleString() : '-'}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '4px' }}>Completed</div>
              <div>{job.completed_at ? new Date(job.completed_at).toLocaleString() : '-'}</div>
            </div>
          </div>
          {job.status === 'running' && (
            <button
              className="btn btn-danger"
              onClick={handleTerminate}
              style={{ marginLeft: '20px' }}
            >
              Terminate Job
            </button>
          )}
        </div>
      </div>

      {/* Ansible output */}
      {(job.output || liveOutput || isStreaming) && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '16px', margin: 0 }}>
              {isStreaming ? 'Live Output (Streaming...)' : 'Ansible Output'}
            </h3>
            {isStreaming && (
              <span className="badge badge-info" style={{ animation: 'pulse 2s infinite' }}>
                ● LIVE
              </span>
            )}
          </div>
          <div className="terminal" ref={outputRef}>
            {liveOutput || job.output || 'Waiting for output...'}
          </div>
        </div>
      )}

      {/* Upgrade readiness results */}
      {job.readiness_json && (
        <>
          <div className="card">
            <h3 style={{ marginBottom: '16px', fontSize: '16px' }}>Upgrade Readiness</h3>

            <div style={{ marginBottom: '20px' }}>
              <strong>Overall Status: </strong>
              <span className={`badge badge-${job.readiness_json.ready ? 'success' : 'danger'}`}>
                {job.readiness_json.ready ? 'READY' : 'NOT READY'}
              </span>
            </div>

            <div>
              <h4 style={{ fontSize: '14px', marginBottom: '12px' }}>Checks</h4>
              {Object.entries(job.readiness_json.checks).map(([key, check]) => (
                <div
                  key={key}
                  style={{
                    border: '1px solid #e2e8f0',
                    padding: '12px',
                    borderRadius: '6px',
                    marginBottom: '12px'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <strong style={{ textTransform: 'capitalize' }}>{key.replace('_', ' ')}</strong>
                    <span className={`badge badge-${check.passed ? 'success' : 'danger'}`}>
                      {check.passed ? 'PASS' : 'FAIL'}
                    </span>
                  </div>
                  <div style={{ fontSize: '14px', color: '#64748b' }}>{check.details}</div>
                  {check.severity && (
                    <div style={{ fontSize: '12px', color: getSeverityColor(check.severity), marginTop: '4px' }}>
                      Severity: {check.severity}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* LLM Summary */}
          {job.llm_summary && (
            <div className="card">
              <h3 style={{ marginBottom: '16px', fontSize: '16px' }}>AI-Generated Summary</h3>
              <div
                style={{
                  background: '#f8fafc',
                  padding: '16px',
                  borderRadius: '6px',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'system-ui'
                }}
              >
                {job.llm_summary}
              </div>
            </div>
          )}
        </>
      )}
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

function getSeverityColor(severity) {
  switch (severity) {
    case 'critical': return '#dc2626'
    case 'warning': return '#ea580c'
    case 'info': return '#2563eb'
    default: return '#64748b'
  }
}
