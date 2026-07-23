import type { Trace } from "../lib/schema";
import { fmtStv } from "../lib/stv";

// Renders a recorded PLN derivation trace: input premises → hop-by-hop derived atoms
// → conclusions → recommendations. Any LLM prose is rendered in a visually distinct
// block, explicitly NOT part of the formal derivation (a hard requirement).
export default function TraceView({ trace }: { trace: Trace }) {
  const eng = trace.engine || {};
  return (
    <div className="trace">
      <div className="trace-meta">
        <span>trace <code>{trace.trace_id}</code></span>
        <span>status <b className={trace.status === "ok" ? "pill ok" : "pill bad"}>{trace.status}</b></span>
        {eng.latency_ms != null && <span>engine {Math.round(eng.latency_ms)} ms</span>}
        {eng.cmd && <span className="muted">{eng.cmd}</span>}
      </div>

      {trace.inputs?.facts?.length ? (
        <div>
          <div className="trace-sec-h">Premises ({trace.inputs.facts.length})</div>
          {trace.inputs.facts.slice(0, 40).map((f, i) => (
            <div className="atomrow" key={i}>{f}</div>
          ))}
        </div>
      ) : null}

      {trace.hops?.length ? (
        <div>
          <div className="trace-sec-h">Derivation — {trace.hops.length} hop{trace.hops.length === 1 ? "" : "s"}</div>
          {trace.hops.map((h) => (
            <div className="hop" key={h.hop}>
              <div className="hop-h">hop {h.hop} · {h.n_new} new of {h.n_premises} premises</div>
              {h.derived.slice(0, 24).map((d, i) => (
                <div className={"atomrow" + (d.new ? " isnew" : "")} key={i}>
                  <span>{d.atom}</span>
                  <span className="stv">{fmtStv(d.stv)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      ) : null}

      {trace.conclusions?.length ? (
        <div>
          <div className="trace-sec-h">Conclusions</div>
          {trace.conclusions.map((c, i) => (
            <div className="concl" key={i}>
              <div className="atomrow">
                <span>{c.atom}</span>
                <span className="stv">{fmtStv(c.stv)}</span>
              </div>
              {(c.rule_id || c.premises?.length) && (
                <div className="muted" style={{ fontSize: 11 }}>
                  {c.rule_id ? `rule ${c.rule_id}` : ""}
                  {c.premises?.length ? ` · from ${c.premises.join(", ")}` : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="empty">No conclusions ({trace.status}).</div>
      )}

      {trace.llm_explanation && (
        <div className="trace-llm">
          <span className="lbl">LLM-generated explanation — not part of the formal derivation</span>
          {trace.llm_explanation}
        </div>
      )}
    </div>
  );
}
