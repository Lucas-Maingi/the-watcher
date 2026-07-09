// the anti-black-box view: the literal graph traversal that produced the
// finding, rendered as hops. every node id here exists in the graph and
// can be queried via /api/graph/node/<id>.
export default function Trace({ steps, root }) {
  return (
    <div>
      <p className="mb-4 text-xs leading-relaxed text-faint">
        how the engine got here — each row is one hop of graph reasoning.
        root node: <span className="font-mono text-accent">{root}</span>
      </p>
      <ol className="space-y-0">
        {steps.map((s, i) => (
          <li key={i} className="relative flex gap-3 pb-4">
            {i < steps.length - 1 && (
              <div className="absolute left-[5px] top-4 h-full w-px bg-line" />
            )}
            <div className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border ${
              i === 0 ? 'border-accent bg-accent/30' : 'border-faint bg-panel-2'
            }`} />
            <div className="min-w-0">
              <div className="font-mono text-xs">
                {s.edge && <span className="text-faint">--[{s.edge}]--&gt; </span>}
                <span className="text-fg">{s.node}</span>
              </div>
              <div className="mt-0.5 text-xs text-dim">{s.note}</div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
