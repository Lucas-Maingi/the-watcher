import { useState } from 'react'
import Severity from './Severity.jsx'
import Trace from './Trace.jsx'

export default function FindingCard({ summary }) {
  const [detail, setDetail] = useState(null)
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('narrative')

  async function toggle() {
    if (!open && !detail) {
      const d = await fetch(`/api/root-causes/${summary.id}`).then(r => r.json())
      setDetail(d)
    }
    setOpen(!open)
  }

  return (
    <div className="overflow-hidden rounded-md border border-line bg-panel">
      <button onClick={toggle} className="block w-full p-5 text-left hover:bg-panel-2/50">
        <div className="flex items-center gap-3">
          <Severity level={summary.severity} />
          <h2 className="text-sm font-medium">{summary.title}</h2>
        </div>
        <div className="mt-2.5 flex gap-5 font-mono text-xs text-dim">
          <span>
            explains <span className="text-accent">{summary.explains_findings}</span> alerts
          </span>
          <span>fix: {summary.fix_effort}</span>
          <span>{summary.services_touched} services touched</span>
          <span className="ml-auto text-faint">{open ? 'collapse' : 'why?'}</span>
        </div>
      </button>

      {open && detail && (
        <div className="border-t border-line">
          <div className="flex border-b border-line font-mono text-xs">
            {['narrative', 'reasoning', 'blast radius', `alerts (${detail.signal_count})`, 'compliance'].map((t, i) => {
              const key = ['narrative', 'reasoning', 'blast', 'alerts', 'compliance'][i]
              return (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`px-4 py-2 ${tab === key ? 'bg-panel-2 text-fg' : 'text-faint hover:text-dim'}`}
                >
                  {t}
                </button>
              )
            })}
          </div>
          <div className="p-5">
            {tab === 'narrative' && (
              <div className="space-y-4 text-sm leading-relaxed text-dim">
                <p className="text-fg">{detail.narrative}</p>
                <div className="rounded border border-line bg-panel-2 p-4">
                  <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-faint">
                    the fix
                  </div>
                  <p>{detail.recommendation}</p>
                </div>
              </div>
            )}
            {tab === 'reasoning' && <Trace steps={detail.trace} root={detail.root_node} />}
            {tab === 'blast' && <BlastRadius br={detail.blast_radius} />}
            {tab === 'alerts' && (
              <ul className="space-y-2">
                {detail.signals.map(s => (
                  <li key={s.id} className="flex items-start gap-2 font-mono text-xs text-dim">
                    <Severity level={s.severity} />
                    <span>{s.message}</span>
                  </li>
                ))}
              </ul>
            )}
            {tab === 'compliance' && (
              <ul className="space-y-2">
                {detail.compliance.map((c, i) => (
                  <li key={i} className="font-mono text-xs text-dim">
                    <span className="text-fg">{c.framework} {c.control}</span> — {c.name}
                  </li>
                ))}
                {detail.compliance.length === 0 && (
                  <li className="text-xs text-faint">no mapped controls for this rule</li>
                )}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function BlastRadius({ br }) {
  return (
    <div className="space-y-4 text-sm">
      <div className="flex gap-8 font-mono text-xs">
        <div>
          <div className="text-faint">effort</div>
          <div className="mt-1 text-lg text-high">{br.effort}</div>
        </div>
        <div>
          <div className="text-faint">services touched</div>
          <div className="mt-1 text-lg text-fg">{br.services_touched.length}</div>
        </div>
      </div>
      <p className="leading-relaxed text-dim">{br.effort_detail}</p>
      <div className="rounded border border-high/30 bg-high/5 p-3 text-xs leading-relaxed text-dim">
        <span className="font-mono uppercase tracking-wider text-high">breakage risk</span>
        <p className="mt-1">{br.breakage_risk}</p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {br.services_touched.map(s => (
          <span key={s} className="rounded bg-panel-2 px-2 py-0.5 font-mono text-[11px] text-dim">
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}
