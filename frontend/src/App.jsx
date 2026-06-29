import { useState, useEffect, useCallback } from 'react'
import KnowledgeHealth from './components/KnowledgeHealth'
import QueryInterface from './components/QueryInterface'
import KnowledgeVoids from './components/KnowledgeVoids'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function App() {
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState(null)
  const [voids, setVoids] = useState([])
  const [voidsError, setVoidsError] = useState(null)
  const [toast, setToast] = useState(null)

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API}/stats`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setStats(await res.json())
      setStatsError(null)
    } catch {
      setStatsError('Could not reach backend at ' + API)
    }
  }, [])

  const fetchVoids = useCallback(async () => {
    try {
      const res = await fetch(`${API}/voids`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setVoids(data.voids || [])
      setVoidsError(null)
    } catch {
      setVoidsError('Could not load knowledge voids')
    }
  }, [])

  useEffect(() => {
    fetchStats()
    fetchVoids()
    const interval = setInterval(fetchVoids, 30000)
    return () => clearInterval(interval)
  }, [fetchStats, fetchVoids])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-500 flex items-center justify-center text-white font-bold text-sm">A</div>
          <div>
            <h1 className="text-lg font-semibold text-white leading-none">Agentic OS</h1>
            <p className="text-xs text-gray-500 mt-0.5">Company Brain — Knowledge Dashboard</p>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <KnowledgeHealth stats={stats} error={statsError} />
        <QueryInterface api={API} onVoidsRefresh={fetchVoids} />
        <KnowledgeVoids voids={voids} error={voidsError} onCreateDoc={showToast} />
      </main>

      {toast && (
        <div className="fixed bottom-6 right-6 bg-indigo-600 text-white px-4 py-2 rounded-lg shadow-lg text-sm">
          {toast}
        </div>
      )}
    </div>
  )
}
