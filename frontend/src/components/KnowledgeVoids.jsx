export default function KnowledgeVoids({ voids, error, onCreateDoc }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-4">
      <div>
        <h2 className="text-base font-semibold text-white">Knowledge Voids</h2>
        <p className="text-xs text-gray-500 mt-0.5">Topics queried repeatedly with no good answers · refreshes every 30s</p>
      </div>

      {error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : voids.length === 0 ? (
        <div className="flex-1 flex items-center justify-center py-8">
          <p className="text-sm text-gray-600">No voids detected yet. Run some queries first.</p>
        </div>
      ) : (
        <div className="space-y-2 overflow-y-auto max-h-[420px] pr-1">
          {voids.map((v, i) => (
            <VoidRow key={v.topic} rank={i + 1} void_={v} onCreateDoc={onCreateDoc} />
          ))}
        </div>
      )}
    </div>
  )
}

function VoidRow({ rank, void_: v, onCreateDoc }) {
  const pct = Math.min(100, Math.round((v.void_score / 10) * 100))

  return (
    <div className="border border-gray-800 rounded-lg p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2 flex-1 min-w-0">
          <span className="text-xs font-mono text-gray-600 mt-0.5 flex-shrink-0">#{rank}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-white truncate">{v.topic}</p>
            <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
              <span>{v.query_count}× queried</span>
              <span>avg score: {v.avg_top_score}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <div className="text-right">
            <div className="text-xs text-gray-500">void score</div>
            <div className="text-sm font-bold text-red-400">{v.void_score.toFixed(1)}</div>
          </div>
          <button
            onClick={() => onCreateDoc('Coming soon')}
            className="text-xs px-2 py-1 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded text-gray-400 hover:text-white transition-colors"
          >
            + Doc
          </button>
        </div>
      </div>

      <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-red-500/60 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
