import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Clusters
export const listClusters = () => api.get('/clusters')
export const getCluster = (id) => api.get(`/clusters/${id}`)
export const createNewCluster = (data) => api.post('/clusters/new', data)
export const registerCluster = (data) => api.post('/clusters/register', data)
export const deleteCluster = (id) => api.delete(`/clusters/${id}`)

// Jobs
export const listJobs = (clusterId = null) => {
  const params = clusterId ? { cluster_id: clusterId } : {}
  return api.get('/jobs', { params })
}
export const getJob = (id) => api.get(`/jobs/${id}`)
export const installCluster = (clusterId) => api.post(`/jobs/install/${clusterId}`)
export const checkUpgradeReadiness = (clusterId) =>
  api.post('/jobs/upgrade-check', { cluster_id: clusterId })

export default api
