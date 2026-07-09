import { useEffect, useState } from 'react'
import FindingCard from './components/FindingCard.jsx'
import RawView from './components/RawView.jsx'
import Landing from './Landing.jsx'

const sevOrder = { critical: 0, high: 1, medium: 2, low: 3 }

// hash routing because react-router would be the biggest dependency in
// the app for exactly two pages
export default function App() {
  const [route, setRoute] = useState(window.location.hash)
  useEffect(() => {
    const onHash = () => setRoute(window.location.hash)
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  return route === '#/app' ? <Dashboard /> : <Landing />
}

function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [findings, setFindings] = useState([])
  const [raw, setRaw] = useState([])
  const [view, setView] = useState('causes') // 'causes' | 'raw'
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      fetch('/api/summary').then(r => r.json()),
      fetch('/api/root-causes').then(r => r.json()),
      fetch('/api/raw-findings').then(r => r.json()),
    ])
      .then(([s, f, r]) => {
        setSummary(s)
        setFindings(f)
        setRaw(r.sort((a, b) => sevOrder[a.severity] - sevOrder[b.severity]))
      })
      .catch(() => setError('backend not reachable - is the api running on :8000?'))
  }, [])

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <header className="mb-10">
        <div className="flex items-baseline justify-between">
          <h1 className="font-mono text-lg tracking-tight">
            <span className="text-accent">the</span>watcher
          </h1>
          {summary && (
            <span className="font-mono text-xs text-faint">
              graph: {summary.graph.nodes} nodes / {summary.graph.edges} edges
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-dim">
          architectural root causes, not alert noise
        </p>
      </header>

      {error && (
        <div className="rounded border border-crit/40 bg-crit/10 p-4 font-mono text-sm text-crit">
          {error}
        </div>
      )}

      {summary && (
        <div className="mb-8 flex items-center gap-6 rounded-md border border-line bg-panel p-5">
          <Stat label="scanner findings" value={summary.raw_findings} dim />
          <div className="font-mono text-2xl text-faint">&rarr;</div>
          <Stat label="root causes" value={summary.root_causes} accent />
          <div className="ml-auto flex rounded border border-line font-mono text-xs">
            <ViewTab active={view === 'causes'} onClick={() => setView('causes')}>
              root causes
            </ViewTab>
            <ViewTab active={view === 'raw'} onClick={() => setView('raw')}>
              raw alerts ({raw.length})
            </ViewTab>
          </div>
        </div>
      )}

      {view === 'causes' ? (
        <div className="space-y-4">
          {findings.map(f => <FindingCard key={f.id} summary={f} />)}
        </div>
      ) : (
        <RawView signals={raw} />
      )}

      <footer className="mt-14 border-t border-line pt-4 font-mono text-xs text-faint">
        every finding above is explainable: expand it and read the actual graph
        traversal that produced it. no scores without reasons.
      </footer>
    </div>
  )
}

function Stat({ label, value, accent, dim }) {
  return (
    <div>
      <div className={`font-mono text-3xl ${accent ? 'text-accent' : dim ? 'text-dim' : ''}`}>
        {value}
      </div>
      <div className="mt-1 text-xs text-faint">{label}</div>
    </div>
  )
}

function ViewTab({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 transition-colors ${
        active ? 'bg-panel-2 text-fg' : 'text-faint hover:text-dim'
      }`}
    >
      {children}
    </button>
  )
}
