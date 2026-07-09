const colors = {
  critical: 'text-crit border-crit/40 bg-crit/10',
  high: 'text-high border-high/40 bg-high/10',
  medium: 'text-med border-med/40 bg-med/10',
  low: 'text-low border-low/40 bg-low/10',
}

export default function Severity({ level }) {
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${colors[level] || ''}`}>
      {level}
    </span>
  )
}
