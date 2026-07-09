// the pitch page. copy rule I set myself: no "empower", no "seamless",
// no "single pane of glass". say the actual thing.
export default function Landing() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <nav className="mb-20 flex items-baseline justify-between">
        <span className="font-mono text-lg tracking-tight">
          <span className="text-accent">the</span>watcher
        </span>
        <a href="#/app" className="font-mono text-xs text-dim hover:text-fg">
          open dashboard &rarr;
        </a>
      </nav>

      <h1 className="text-3xl font-medium leading-snug">
        Your scanner found 200 problems.
        <br />
        <span className="text-dim">Your architecture has about five.</span>
      </h1>

      <p className="mt-8 max-w-xl leading-relaxed text-dim">
        Security scanners are honest and useless in the same breath: every alert
        is technically true, and none of them tells you that 40 of them are the
        same copy-pasted Terraform module wearing different service names. The
        alerts aren&apos;t the problem. They&apos;re the symptom feed.
      </p>

      <p className="mt-4 max-w-xl leading-relaxed text-dim">
        The Watcher builds one structural graph across your repos, CI pipelines
        and cloud config, then reasons over it the way a security architect
        does: <span className="text-fg">what single decision, template or
        shortcut is generating this whole class of findings?</span> You fix the
        pattern once. The 40 alerts don&apos;t come back.
      </p>

      <div className="mt-12 grid gap-4 sm:grid-cols-3">
        <Card title="shows its work">
          Every finding carries the literal graph traversal that produced it.
          Click &quot;why&quot; and read the hops. No black-box severity scores.
        </Card>
        <Card title="counts the cost">
          Recommendations come with blast radius: which services a fix touches,
          effort in honest bands, what&apos;s likely to break.
        </Card>
        <Card title="speaks agent">
          The reasoning engine is exposed as MCP tools. Your coding agent asks
          what affects the file it&apos;s editing and gets root causes, not lint.
        </Card>
      </div>

      <div className="mt-12 rounded-md border border-line bg-panel p-6">
        <div className="font-mono text-xs text-faint">the demo, in one number</div>
        <div className="mt-3 flex items-baseline gap-4 font-mono">
          <span className="text-4xl text-dim">56</span>
          <span className="text-faint">scanner alerts</span>
          <span className="text-2xl text-faint">&rarr;</span>
          <span className="text-4xl text-accent">6</span>
          <span className="text-faint">root causes, each with the one fix</span>
        </div>
        <a
          href="#/app"
          className="mt-6 inline-block rounded border border-accent/50 bg-accent/10 px-4 py-2 font-mono text-sm text-accent hover:bg-accent/20"
        >
          see it on the demo company &rarr;
        </a>
      </div>

      <footer className="mt-20 border-t border-line pt-4 font-mono text-xs text-faint">
        runs entirely locally. read-only connectors. your cloud credentials
        never leave your machine.
      </footer>
    </div>
  )
}

function Card({ title, children }) {
  return (
    <div className="rounded-md border border-line bg-panel p-4">
      <div className="mb-2 font-mono text-xs text-accent">{title}</div>
      <p className="text-xs leading-relaxed text-dim">{children}</p>
    </div>
  )
}
