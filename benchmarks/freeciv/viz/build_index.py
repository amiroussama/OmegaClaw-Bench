"""Build the viz data index for the FreeCiv benchmark webpage.

Scans benchmarks/freeciv/ab_runs/ and normalizes the several on-disk run layouts (A/B parallel,
head-to-head duel with g1/g2 subdirs, and old committed-only duel) into ONE page-friendly file:
benchmarks/freeciv/viz/data/index.json. The page then never has to know disk quirks, and the
gitignored/root-owned raw duel.jsonl is read once here rather than by the browser.

Reuses the existing stat engines (run_summary.summarize_side) instead of recomputing verdicts.
Also folds in the static KPI micro-benchmarks (results.json, turn_cycle_results.json).

Stdlib only. Usage: python3 benchmarks/freeciv/viz/build_index.py [--out PATH]
"""

# --- OmegaClaw-Bench core-path bootstrap (added by the benchmarks<->core split) ---
import os as _ocp, sys as _scp
_cp_root = _ocp.path.dirname(_ocp.path.abspath(__file__))
while _cp_root != _ocp.path.dirname(_cp_root):
    if _ocp.path.isdir(_ocp.path.join(_cp_root, "core", "src")):
        break
    _cp_root = _ocp.path.dirname(_cp_root)
for _cp in (_ocp.path.join(_cp_root, "core", "src"), _ocp.path.join(_cp_root, "core")):
    if _cp not in _scp.path:
        _scp.path.insert(0, _cp)
# --- end OmegaClaw-Bench core-path bootstrap ---


import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))            # benchmarks/freeciv/viz
_FREECIV = os.path.dirname(_HERE)                             # benchmarks/freeciv
if _FREECIV not in sys.path:
    sys.path.insert(0, _FREECIV)

import run_summary as rs  # noqa: E402

_AB_RUNS = os.path.join(_FREECIV, "ab_runs")
_TRAJ_METRICS = ("n_cities", "n_units", "n_techs")


# --------------------------------------------------------------------------- duel (raw g1/g2)

def _side(r, i):
    return r.get("side%d" % i)


def _traj_point(t, s):
    m = s.get("metrics") or {}
    return {"turn": t,
            "n_cities": m.get("n_cities"), "n_units": m.get("n_units"), "n_techs": m.get("n_techs"),
            "proposed": s.get("proposed"), "submitted": s.get("submitted"),
            "blocked": s.get("blocked"), "n_conclusions": s.get("n_conclusions"),
            "reason_ms": s.get("reason_ms"), "llm_ms": s.get("llm_ms")}


def _side_stats(rows, side_i):
    """rs.summarize_side + a few aggregate activity stats for one side of a duel game."""
    base = rs.summarize_side(
        rows,
        turn_of=lambda r: r.get("turn"),
        metrics_of=lambda r, i=side_i: (_side(r, i) or {}).get("metrics"),
        proposed_of=lambda r, i=side_i: (_side(r, i) or {}).get("proposed"),
        nconc_of=lambda r, i=side_i: (_side(r, i) or {}).get("n_conclusions"),
    ) or {}
    withm = [r for r in rows if _side(r, side_i) and (_side(r, side_i).get("metrics"))]
    proposed = sum((_side(r, side_i).get("proposed") or 0) for r in withm)
    blocked = sum((_side(r, side_i).get("blocked") or 0) for r in withm)
    submitted = sum((_side(r, side_i).get("submitted") or 0) for r in withm)
    llm = [(_side(r, side_i).get("llm_ms")) for r in withm]
    rms = [(_side(r, side_i).get("reason_ms")) for r in withm]
    base.update({
        "proposed": proposed, "submitted": submitted, "blocked": blocked,
        "illegal_rate": round(blocked / proposed, 3) if proposed else 0.0,
        "avg_llm_ms": _avg(llm), "avg_reason_ms": _avg(rms),
    })
    return base


def _avg(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 1) if xs else None


# --------------------------------------------------------------------------- traces + snapshot (#2/#4)

def _referenced_trace_ids(moves):
    """Every trace_id referenced by a game's move records (pln + plain slots)."""
    ids = set()
    for mv in moves or []:
        for arm in ("pln", "plain"):
            for a in mv.get(arm) or []:
                if a.get("trace_id"):
                    ids.add(a["trace_id"])
    return ids


def _load_traces(traces_dir, trace_ids):
    """Load only the referenced PLN trace records from ``traces_dir`` (bounds index.json size)."""
    out = {}
    for tid in trace_ids:
        p = os.path.join(traces_dir, "%s.json" % tid)
        if os.path.isfile(p):
            try:
                out[tid] = json.load(open(p, encoding="utf-8"))
            except (ValueError, OSError):
                pass
    return out


def _load_snapshot(run_dir):
    """The per-run AtomSpace snapshot (Issue #2) if present, else None."""
    for name in ("atomspace_latest.json",):
        p = os.path.join(run_dir, name)
        if os.path.isfile(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except (ValueError, OSError):
                return None
    return None


def _duel_game_from_raw(base_dir, subdir, pln_side):
    rows = [r for r in rs.load_jsonl(os.path.join(base_dir, subdir, "duel.jsonl")) if "side0" in r]
    if not rows:
        return None
    pln_i, plain_i = (0, 1) if pln_side == 0 else (1, 0)
    traj = {"pln": [], "plain": []}
    moves = []
    for r in rows:
        t = r.get("turn")
        sp, sq = _side(r, pln_i) or {}, _side(r, plain_i) or {}
        if sp.get("metrics"):
            traj["pln"].append(_traj_point(t, sp))
        if sq.get("metrics"):
            traj["plain"].append(_traj_point(t, sq))
        pm, qm = sp.get("moves") or [], sq.get("moves") or []
        if pm or qm:
            moves.append({"turn": t, "pln": pm, "plain": qm,
                          "recommendations": sp.get("recommendations") or []})
    pln_stats, plain_stats = _side_stats(rows, pln_i), _side_stats(rows, plain_i)
    winner = rs.territory_winner(pln_stats.get("final"), plain_stats.get("final"))
    game_dir = os.path.join(base_dir, subdir)
    traces = _load_traces(os.path.join(game_dir, "traces"), _referenced_trace_ids(moves))
    return {"subdir": subdir, "pln_side": pln_side,
            "trajectory": traj, "moves": moves,
            "stats": {"pln": pln_stats, "plain": plain_stats}, "winner": winner,
            "traces": traces, "atomspace": _load_snapshot(game_dir),
            "moves_logged": bool(moves)}


def _duel_run(run_dir, run_id):
    """Prefer raw g1/g2 duel.jsonl; fall back to committed duel_comparison.json games[]."""
    games, has_raw = [], False
    for subdir, pln_side in (("g1", 0), ("g2", 1)):
        if os.path.isfile(os.path.join(run_dir, subdir, "duel.jsonl")):
            g = _duel_game_from_raw(run_dir, subdir, pln_side)
            if g:
                games.append(g); has_raw = True
    source = "raw"
    if not games:
        cmp_path = os.path.join(run_dir, "duel_comparison.json")
        if os.path.isfile(cmp_path):
            payload = json.load(open(cmp_path, encoding="utf-8"))
            source = "committed"
            for g in payload.get("games", []):
                games.append({"subdir": g.get("subdir"), "pln_side": g.get("pln_side"),
                              "trajectory": {"pln": [], "plain": []}, "moves": [],
                              "stats": {"pln": g.get("pln"), "plain": g.get("plain")},
                              "winner": g.get("winner_arm"), "moves_logged": False})
    if not games:
        return None
    pln_wins = sum(1 for g in games if g["winner"] == "pln")
    plain_wins = sum(1 for g in games if g["winner"] == "plain")
    return {"id": run_id, "type": "duel", "source": source, "games": games,
            "pln_wins": pln_wins, "plain_wins": plain_wins,
            "verdict": _duel_verdict(pln_wins, plain_wins, len(games)),
            "has_moves": any(g["moves_logged"] for g in games)}


def _duel_verdict(pln_wins, plain_wins, n):
    if n and pln_wins == n:
        return "PLN wins all %d mirror game(s)" % n
    if n and plain_wins == n:
        return "plain wins all %d mirror game(s)" % n
    if pln_wins == plain_wins:
        return "split %d-%d" % (pln_wins, plain_wins)
    return "PLN %d / plain %d of %d games" % (pln_wins, plain_wins, n)


# --------------------------------------------------------------------------- A/B (comparison.json)

def _ab_run(run_dir, run_id):
    cmp_path = os.path.join(run_dir, "comparison.json")
    payload = json.load(open(cmp_path, encoding="utf-8"))
    stats = payload.get("stats", {})
    traj = payload.get("trajectory", {})
    # 3-arm comparison.json carries "arms"/"contrast"; legacy 2-arm dirs default to pln/plain.
    arms = payload.get("arms") or ["pln", "plain"]
    contrast = payload.get("contrast") or ["pln", "plain"]
    a_name, b_name = contrast[0], contrast[-1]

    def _pts(arm):
        out = []
        for p in traj.get(arm, []):
            out.append({"turn": p.get("turn"),
                        **{k: p.get(k) for k in _TRAJ_METRICS}})
        return out

    overall = payload.get("overall")
    wins = payload.get("verdict_wins") or {}
    verdict = ("overall winner: %s (%s vs %s) %s" % (overall, a_name, b_name, wins)
               if overall else "A/B (no verdict)")
    # Map the primary contrast (chaining vs facts-only) onto the page's pln/plain slots, and expose
    # the full arm set for a 3-arm view.
    game = {"subdir": None, "pln_side": None,
            "trajectory": {"pln": _pts(a_name), "plain": _pts(b_name)}, "moves": [],
            "stats": {"pln": stats.get(a_name), "plain": stats.get(b_name)},
            "arms": arms, "contrast": contrast,
            "trajectory_all": {a: _pts(a) for a in arms},
            "stats_all": {a: stats.get(a) for a in arms},
            "winner": overall, "moves_logged": False}

    # Per-unit moves + PLN traces come from the raw arm JSONL (comparison.json carries none), so an
    # A/B run is inspectable — not just its aggregates. The pln slot = the contrast's chaining arm.
    moves = _ab_moves(run_dir, a_name, b_name)
    if moves:
        game["moves"] = moves
        game["moves_logged"] = True
        game["traces"] = _load_traces(os.path.join(run_dir, "traces"), _referenced_trace_ids(moves))
    game["atomspace"] = _load_snapshot(run_dir)
    return {"id": run_id, "type": "ab", "source": "comparison.json", "games": [game],
            "arms": arms, "contrast": contrast, "verdict": verdict,
            "has_moves": bool(game["moves_logged"])}


def _ab_moves(run_dir, a_name, b_name):
    """Per-turn moves for the A/B contrast, pln slot = ``a_name`` arm, plain slot = ``b_name``."""
    def _by_turn(arm):
        rows = {}
        for r in rs.load_jsonl(os.path.join(run_dir, "%s.jsonl" % arm)):
            if "metrics" not in r:
                continue
            rows[r.get("advanced_to") or r.get("turn")] = r
        return rows
    a_rows, b_rows = _by_turn(a_name), _by_turn(b_name)
    turns = sorted(t for t in set(a_rows) | set(b_rows) if t is not None)
    moves = []
    for t in turns:
        ar, br = a_rows.get(t, {}), b_rows.get(t, {})
        pm, qm = ar.get("moves") or [], br.get("moves") or []
        if pm or qm:
            moves.append({"turn": t, "pln": pm, "plain": qm,
                          "recommendations": ar.get("recommendations") or []})
    return moves


# --------------------------------------------------------------------------- fixtures (static KPI)

def _fixtures():
    out = []
    for fname, label in (("results.json", "adapter/validation (#6)"),
                         ("turn_cycle_results.json", "turn-cycle (#25)")):
        path = os.path.join(_FREECIV, fname)
        if os.path.isfile(path):
            try:
                d = json.load(open(path, encoding="utf-8"))
                out.append({"id": fname, "label": label,
                            "summary": d.get("summary"), "rows": d.get("rows")})
            except (ValueError, OSError):
                pass
    return out


# --------------------------------------------------------------------------- driver

def _classify(run_dir):
    if os.path.isfile(os.path.join(run_dir, "comparison.json")):
        return "ab"
    if (os.path.isfile(os.path.join(run_dir, "g1", "duel.jsonl"))
            or os.path.isfile(os.path.join(run_dir, "g2", "duel.jsonl"))
            or os.path.isfile(os.path.join(run_dir, "duel_comparison.json"))):
        return "duel"
    return None


def _add_run(runs, run_dir, name):
    kind = _classify(run_dir)
    try:
        run = _ab_run(run_dir, name) if kind == "ab" else \
              _duel_run(run_dir, name) if kind == "duel" else None
    except (ValueError, OSError, KeyError) as e:
        sys.stderr.write("skip %s: %s\n" % (name, e)); run = None
    if run:
        runs.append(run)


def build():
    runs = []
    if os.path.isdir(_AB_RUNS):
        for name in sorted(os.listdir(_AB_RUNS)):
            run_dir = os.path.join(_AB_RUNS, name)
            if not os.path.isdir(run_dir):
                continue  # skip LATEST / LATEST_DUEL pointer files
            # Batch layout: batch_<ts>/seed<n>/{duel,ab} — one catalog entry per game type per seed.
            if name.startswith("batch_") and _classify(run_dir) is None:
                for seed in sorted(os.listdir(run_dir)):
                    if not seed.startswith("seed"):
                        continue
                    _add_run(runs, os.path.join(run_dir, seed, "duel"), "%s · %s · duel" % (name, seed))
                    _add_run(runs, os.path.join(run_dir, seed, "ab"), "%s · %s · ab" % (name, seed))
                continue
            _add_run(runs, run_dir, name)
    # newest first (dir names are UTC timestamps, optionally prefixed)
    runs.sort(key=lambda r: r["id"], reverse=True)
    return {"generated": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "runs": runs, "fixtures": _fixtures()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(_HERE, "data", "index.json"))
    args = ap.parse_args()
    payload = build()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    n_moves = sum(1 for r in payload["runs"] if r.get("has_moves"))
    print("wrote %s — %d run(s) [%d with per-unit moves], %d fixture set(s)" %
          (args.out, len(payload["runs"]), n_moves, len(payload["fixtures"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
