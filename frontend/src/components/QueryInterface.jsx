import { useState } from 'react'

export default function QueryInterface({ api, onVoidsRefresh }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${api}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query.trim(),
          user_id: 'dashboard',
          groups: ['engineering'],
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setResults(data.results || [])
      onVoidsRefresh()
    } catch {
      setError('Query failed — is the backend running?')
      setResults(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-4">
      <div>
        <h2 className="text-base font-semibold text-white">Query Interface</h2>
        <p className="text-xs text-gray-500 mt-0.5">Search the knowledge base with composite scoring</p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="e.g. token expiry policy"
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg text-sm font-medium text-white transition-colors"
        >
          {loading ? '…' : 'Search'}
        </button>
      </form>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {results !== null && (
        <div className="space-y-3 overflow-y-auto max-h-[420px] pr-1">
          {results.length === 0 ? (
            <p className="text-sm text-gray-500">No results found.</p>
          ) : (
            results.map(r => <ResultCard key={r.artifact_id} result={r} />)
          )}
        </div>
      )}
    </div>
  )
}

function ResultCard({ result }) {
  const score = result.scores.composite
  const scoreColor = score > 0.6 ? 'bg-emerald-500' : score > 0.3 ? 'bg-yellow-500' : 'bg-red-500'
  const scorePct = Math.round(score * 100)

  return (
    <div className="border border-gray-800 rounded-lg p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{result.title || result.artifact_id}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">{result.source}</span>
            <span className="text-xs text-gray-600">{result.event_type}</span>
          </div>
        </div>
        <div className="flex-shrink-0 text-right">
          <div className="text-xs text-gray-500">composite</div>
          <div className="text-sm font-bold text-white">{score.toFixed(3)}</div>
        </div>
      </div>

      {/* Score bar */}
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${scoreColor}`} style={{ width: `${scorePct}%` }} />
      </div>

      <p className="text-xs text-gray-500 line-clamp-2">{result.content_excerpt}</p>

      {result.freshness_warning && (
        <div className="flex items-center gap-1.5 text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800/30 rounded px-2 py-1">
          <span>⚠</span> {result.freshness_warning}
        </div>
      )}
      {result.contradiction_alert && (
        <div className="flex items-center gap-1.5 text-xs text-red-400 bg-red-900/20 border border-red-800/30 rounded px-2 py-1">
          <span>✕</span> {result.contradiction_alert}
        </div>
      )}
    </div>
  )
}
