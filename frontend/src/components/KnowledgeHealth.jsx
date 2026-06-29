export default function KnowledgeHealth({ stats, error }) {
  const total = stats?.total_artifacts ?? 0
  const buckets = stats?.temperature_buckets ?? { hot: 0, warm: 0, cold: 0 }
  const hotPct = total ? Math.round((buckets.hot / total) * 100) : 0
  const warmPct = total ? Math.round((buckets.warm / total) * 100) : 0
  const coldPct = total ? Math.round((buckets.cold / total) * 100) : 0

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-4">
      <div>
        <h2 className="text-base font-semibold text-white">Knowledge Health</h2>
        <p className="text-xs text-gray-500 mt-0.5">Freshness distribution across indexed artifacts</p>
      </div>

      {error ? (
        <p className="text-sm text-red-400">{error}</p>
      ) : !stats ? (
        <p className="text-sm text-gray-500 animate-pulse">Loading…</p>
      ) : (
        <>
          <div className="text-3xl font-bold text-white">
            {total}
            <span className="text-sm font-normal text-gray-500 ml-2">artifacts indexed</span>
          </div>

          {/* Bar chart */}
          <div className="space-y-3">
            <TemperatureBar label="Hot (>0.8)" count={buckets.hot} pct={hotPct} color="bg-emerald-500" />
            <TemperatureBar label="Warm (0.5–0.8)" count={buckets.warm} pct={warmPct} color="bg-yellow-500" />
            <TemperatureBar label="Cold (≤0.5)" count={buckets.cold} pct={coldPct} color="bg-red-500" />
          </div>

          <div className="text-xs text-gray-600 pt-1">
            Temperature decays at k=0.01/day · ambient floor 0.10
          </div>
        </>
      )}
    </div>
  )
}

function TemperatureBar({ label, count, pct, color }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>{label}</span>
        <span>{count} ({pct}%)</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
