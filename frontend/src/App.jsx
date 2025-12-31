import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Credentials from './pages/Credentials'
import Clusters from './pages/Clusters'
import ClusterDetail from './pages/ClusterDetail'
import NewCluster from './pages/NewCluster'
import RegisterCluster from './pages/RegisterCluster'
import Jobs from './pages/Jobs'
import JobDetail from './pages/JobDetail'

function App() {
  return (
    <Router>
      <div className="app">
        <aside className="sidebar">
          <h1>RKE2 Automation</h1>
          <nav>
            <NavLink to="/">Dashboard</NavLink>
            <NavLink to="/credentials">Credentials</NavLink>
            <NavLink to="/clusters">Clusters</NavLink>
            <NavLink to="/new-cluster">New Cluster</NavLink>
            <NavLink to="/register-cluster">Register Cluster</NavLink>
            <NavLink to="/jobs">Jobs</NavLink>
          </nav>
        </aside>
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/credentials" element={<Credentials />} />
            <Route path="/clusters" element={<Clusters />} />
            <Route path="/clusters/:clusterId" element={<ClusterDetail />} />
            <Route path="/new-cluster" element={<NewCluster />} />
            <Route path="/register-cluster" element={<RegisterCluster />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/jobs/:jobId" element={<JobDetail />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

export default App
