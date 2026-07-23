import type { LintFinding } from "../lib/schema";

export default function LintBanner({ ok, findings }: { ok: boolean; findings: LintFinding[] }) {
  const errs = findings.filter((f) => f.severity === "error").length;
  const warns = findings.filter((f) => f.severity === "warn").length;
  return (
    <div className={"lint " + (ok ? "ok" : "issues")}>
      <div style={{ fontWeight: 600, marginBottom: findings.length ? 6 : 0 }}>
        {ok ? "✓ Lint clean" : `⚠ Lint: ${errs} error${errs === 1 ? "" : "s"}, ${warns} warning${warns === 1 ? "" : "s"}`}
      </div>
      {findings.map((f, i) => (
        <div className={"f f-" + f.severity} key={i}>
          <span className="sev">{f.severity}</span>
          <span>
            <b>{f.check}</b> — {f.message}
            {f.atom_ids?.length ? <span className="muted"> ({f.atom_ids.join(", ")})</span> : null}
          </span>
        </div>
      ))}
    </div>
  );
}
