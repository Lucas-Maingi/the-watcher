import Severity from './Severity.jsx'

// the "before" picture: what living with a conventional scanner feels
// like. intentionally exhausting to scroll - that's the point.
export default function RawView({ signals }) {
  return (
    <div>
      <p className="mb-4 text-xs leading-relaxed text-faint">
        this is the same system as the root-cause view — rendered the way a
        conventional scanner reports it. {signals.length} alerts, most of them
        the same few diseases wearing different names.
      </p>
      <ul className="divide-y divide-line rounded-md border border-line bg-panel">
        {signals.map(s => (
          <li key={s.id} className="flex items-start gap-3 p-3">
            <Severity level={s.severity} />
            <div className="min-w-0">
              <div className="text-xs text-fg">{s.message}</div>
              <div className="mt-0.5 font-mono text-[10px] text-faint">
                {s.rule} · {s.resource}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
