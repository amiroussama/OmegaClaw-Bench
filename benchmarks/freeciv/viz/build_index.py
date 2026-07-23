"""Build the viz data for the FreeCiv benchmark dashboard (React app data layer).

Scans benchmarks/freeciv/ab_runs/ and normalizes the on-disk run layouts (A/B parallel,
head-to-head duel g1/g2, old committed-only duel, and batch_<ts>/seed<n>/{ab,duel}) into:

  data/index.json          — a light CATALOG: one entry per run (+ a `detail` path), the batch
                             aggregates, and the static KPI fixtures. The app loads this first.
  data/runs/<safe_id>.json — the heavy per-run DETAIL (all-arm per-turn series, per-unit moves,
                             PLN traces, and the per-turn AtomSpace timeline), fetched on demand.

Splitting keeps index.json small even with many batch seeds × arms × turns. Stdlib only.
Usage: python3 benchmarks/freeciv/viz/build_index.py [--out-dir DIR]
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
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))            # benchmarks/freeciv/viz
_FREECIV = os.path.dirname(_HERE)                             # benchmarks/freeciv
if _FREECIV not in sys.path:
    sys.path.insert(0, _FREECIV)

import run_summary as rs  # noqa: E402

_AB_RUNS = os.path.join(_FREECIV, "ab_runs")
_TRAJ_METRICS = ("n_cities", "n_units", "n_techs")


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _avg(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 1) if xs else None


# --------------------------------------------------------------------------- shared: traces + atoms

def _referenced_trace_ids(moves):
    ids = set()
    for mv in moves or []:
        for slot in ("pln", "plain"):
            for a in mv.get(slot) or []:
                if a.get("trace_id"):
                    ids.add(a["trace_id"])
    return ids


def _load_traces(traces_dir, trace_ids):
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
    p = os.path.join(run_dir, "atomspace_latest.json")
    if os.path.isfile(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except (ValueError, OSError):
            return None
    return None


def _load_atom_timeline(run_dir):
    """Per-turn AtomSpace snapshots: {turn: snapshot} from atomspace_turn<N>.json."""
    timeline = {}
    if not os.path.isdir(run_dir):
        return timeline
    for fn in os.listdir(run_dir):
        m = re.match(r"atomspace_turn(\d+)\.json$", fn)
        if not m:
            continue
        try:
            timeline[m.group(1)] = json.load(open(os.path.join(run_dir, fn), encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return timeline


# --------------------------------------------------------------------------- duel (raw g1/g2)

def _side(r, i):
    return r.get("side%d" % i)


def _traj_point(t, s):
    m = s.get("metrics") or {}
    return {"turn": t,
            "n_cities": m.get("n_cities"), "n_units": m.get("n_units"), "n_techs": m.get("n_techs"),
            "proposed": s.get("proposed"), "submitted": s.get("submitted"),
            "blocked": s.get("blocked"), "n_conclusions": s.get("n_conclusions"),
            "illegal_rate": (round((s.get("blocked") or 0) / s.get("proposed"), 3) if s.get("proposed") else 0.0),
            "reason_ms": s.get("reason_ms"), "llm_ms": s.get("llm_ms")}


def _side_stats(rows, side_i):
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
    base.update({
        "proposed": proposed, "submitted": submitted, "blocked": blocked,
        "illegal_rate": round(blocked / proposed, 3) if proposed else 0.0,
        "avg_llm_ms": _avg([(_side(r, side_i).get("llm_ms")) for r in withm]),
        "avg_reason_ms": _avg([(_side(r, side_i).get("reason_ms")) for r in withm]),
    })
    return base


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
            moves.append({"turn": t, "pln": pm, "plain": qm, "recommendations": sp.get("recommendations") or []})
    pln_stats, plain_stats = _side_stats(rows, pln_i), _side_stats(rows, plain_i)
    winner = rs.territory_winner(pln_stats.get("final"), plain_stats.get("final"))
    game_dir = os.path.join(base_dir, subdir)
    return {"subdir": subdir, "pln_side": pln_side,
            "trajectory": traj, "series_all": {"pln": traj["pln"], "plain": traj["plain"]},
            "moves": moves, "stats": {"pln": pln_stats, "plain": plain_stats},
            "stats_all": {"pln": pln_stats, "plain": plain_stats}, "winner": winner,
            "traces": _load_traces(os.path.join(game_dir, "traces"), _referenced_trace_ids(moves)),
            "atomspace": _load_snapshot(game_dir), "atom_timeline": _load_atom_timeline(game_dir),
            "moves_logged": bool(moves)}


def _duel_run(run_dir, run_id):
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
                              "trajectory": {"pln": [], "plain": []}, "series_all": {},
                              "moves": [], "stats": {"pln": g.get("pln"), "plain": g.get("plain")},
                              "stats_all": {"pln": g.get("pln"), "plain": g.get("plain")},
                              "winner": g.get("winner_arm"), "moves_logged": False})
    if not games:
        return None
    pln_wins = sum(1 for g in games if g["winner"] == "pln")
    plain_wins = sum(1 for g in games if g["winner"] == "plain")
    return {"id": run_id, "type": "duel", "source": source, "arms": ["pln", "plain"],
            "contrast": ["pln", "plain"], "games": games,
            "verdict": _duel_verdict(pln_wins, plain_wins, len(games)),
            "overall": ("pln" if pln_wins > plain_wins else "plain" if plain_wins > pln_wins else "tie"),
            "has_moves": any(g["moves_logged"] for g in games),
            "has_atoms": any(g.get("atomspace") or g.get("atom_timeline") for g in games)}


def _duel_verdict(pln_wins, plain_wins, n):
    if n and pln_wins == n:
        return "PLN wins all %d mirror game(s)" % n
    if n and plain_wins == n:
        return "plain wins all %d mirror game(s)" % n
    if pln_wins == plain_wins:
        return "split %d-%d" % (pln_wins, plain_wins)
    return "PLN %d / plain %d of %d games" % (pln_wins, plain_wins, n)


# --------------------------------------------------------------------------- A/B (comparison.json)

def _ab_series(run_dir, arm):
    """Full per-turn series for one arm from its raw JSONL (metrics + activity)."""
    pts = []
    for r in rs.load_jsonl(os.path.join(run_dir, "%s.jsonl" % arm)):
        if "metrics" not in r:
            continue
        m = r.get("metrics") or {}
        pts.append({"turn": r.get("advanced_to") or r.get("turn"),
                    "n_cities": m.get("n_cities"), "n_units": m.get("n_units"), "n_techs": m.get("n_techs"),
                    "n_conclusions": r.get("n_conclusions"), "proposed": r.get("proposed"),
                    "submitted": r.get("submitted"), "blocked": r.get("blocked"),
                    "illegal_rate": r.get("illegal_rate"), "reason_ms": r.get("reason_ms"),
                    "llm_ms": r.get("llm_ms"), "hops": r.get("hops")})
    pts = [p for p in pts if p["turn"] is not None]
    pts.sort(key=lambda p: p["turn"])
    return pts


def _ab_moves(run_dir, a_name, b_name):
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
            moves.append({"turn": t, "pln": pm, "plain": qm, "recommendations": ar.get("recommendations") or []})
    return moves


def _discover_arms(run_dir):
    """Every arm that produced a <arm>.jsonl in the run dir (comparison.json may list fewer)."""
    return sorted(fn[:-6] for fn in os.listdir(run_dir) if fn.endswith(".jsonl"))


def _ab_run(run_dir, run_id):
    payload = json.load(open(os.path.join(run_dir, "comparison.json"), encoding="utf-8"))
    stats = dict(payload.get("stats", {}))
    contrast = payload.get("contrast") or ["pln", "plain"]
    a_name, b_name = contrast[0], contrast[-1]
    # Union comparison arms with any extra arm that logged a JSONL (e.g. facts+chaining-v2, which
    # ab_report.py's 3-arm comparison.json does not list) so the A/B view shows every arm run.
    arms = payload.get("arms") or ["pln", "plain"]
    for a in _discover_arms(run_dir):
        if a not in arms:
            arms.append(a)

    # Prefer full per-turn series from raw JSONL (metrics + activity); fall back to comparison.json.
    series_all = {}
    for arm in arms:
        s = _ab_series(run_dir, arm)
        if not s:
            s = [{"turn": p.get("turn"), **{k: p.get(k) for k in _TRAJ_METRICS}}
                 for p in payload.get("trajectory", {}).get(arm, [])]
        series_all[arm] = s

    def _traj(arm):
        return [{"turn": p.get("turn"), **{k: p.get(k) for k in _TRAJ_METRICS}} for p in series_all.get(arm, [])]

    overall = payload.get("overall")
    wins = payload.get("verdict_wins") or {}
    verdict = ("overall winner: %s (%s vs %s) %s" % (overall, a_name, b_name, wins)
               if overall else "A/B (no verdict)")

    # arms absent from comparison.json (v2) get a minimal final-state stat from their series tail.
    for a in arms:
        if not stats.get(a) and series_all.get(a):
            last = series_all[a][-1]
            rms = [p.get("reason_ms") for p in series_all[a]]
            stats[a] = {"final": {"n_cities": last.get("n_cities"), "n_units": last.get("n_units"),
                                  "n_techs": last.get("n_techs")},
                        "illegal_rate": last.get("illegal_rate"), "avg_reason_ms": _avg(rms)}

    moves = _ab_moves(run_dir, a_name, b_name)
    game = {"subdir": None, "pln_side": None,
            "trajectory": {"pln": _traj(a_name), "plain": _traj(b_name)},
            "series_all": series_all,
            "moves": moves,
            "stats": {"pln": stats.get(a_name), "plain": stats.get(b_name)},
            "stats_all": {a: stats.get(a) for a in arms},
            "arms": arms, "contrast": contrast, "winner": overall, "moves_logged": bool(moves),
            "traces": _load_traces(os.path.join(run_dir, "traces"), _referenced_trace_ids(moves)),
            "atomspace": _load_snapshot(run_dir), "atom_timeline": _load_atom_timeline(run_dir)}
    return {"id": run_id, "type": "ab", "source": "comparison.json", "arms": arms, "contrast": contrast,
            "games": [game], "verdict": verdict, "overall": overall,
            "has_moves": bool(game["moves_logged"]),
            "has_atoms": bool(game["atomspace"] or game["atom_timeline"])}


# --------------------------------------------------------------------------- fixtures / batches

def _fixtures():
    out = []
    for fname, label in (("results.json", "adapter/validation (#6)"),
                         ("turn_cycle_results.json", "turn-cycle (#25)")):
        path = os.path.join(_FREECIV, fname)
        if os.path.isfile(path):
            try:
                d = json.load(open(path, encoding="utf-8"))
                out.append({"id": fname, "label": label, "summary": d.get("summary"), "rows": d.get("rows")})
            except (ValueError, OSError):
                pass
    return out


def _batches():
    out = []
    if not os.path.isdir(_AB_RUNS):
        return out
    for name in sorted(os.listdir(_AB_RUNS), reverse=True):
        agg = os.path.join(_AB_RUNS, name, "aggregate.json")
        if name.startswith("batch_") and os.path.isfile(agg):
            try:
                payload = json.load(open(agg, encoding="utf-8"))
            except (ValueError, OSError):
                continue
            # Only the current contrast-keyed shape (ab = {contrast: summary}); skip the legacy
            # 2-arm aggregate whose "ab" is a single summary (would break the contrast views).
            ab = payload.get("ab")
            if isinstance(ab, dict) and ab and all(isinstance(v, dict) and "n_games" in v for v in ab.values()):
                out.append({"id": name, "safe_id": _safe(name), "aggregate": payload})
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


def _make_run(run_dir, run_id):
    kind = _classify(run_dir)
    try:
        if kind == "ab":
            return _ab_run(run_dir, run_id)
        if kind == "duel":
            return _duel_run(run_dir, run_id)
    except (ValueError, OSError, KeyError) as e:
        sys.stderr.write("skip %s: %s\n" % (run_id, e))
    return None


def _collect_runs():
    runs = []
    if os.path.isdir(_AB_RUNS):
        for name in sorted(os.listdir(_AB_RUNS)):
            run_dir = os.path.join(_AB_RUNS, name)
            if not os.path.isdir(run_dir):
                continue
            if name.startswith("batch_") and _classify(run_dir) is None:
                for seed in sorted(os.listdir(run_dir)):
                    if not seed.startswith("seed"):
                        continue
                    for kind in ("ab", "duel"):
                        r = _make_run(os.path.join(run_dir, seed, kind), "%s · %s · %s" % (name, seed, kind))
                        if r:
                            r["batch"], r["seed"] = name, seed
                            runs.append(r)
                continue
            r = _make_run(run_dir, name)
            if r:
                runs.append(r)
    runs.sort(key=lambda r: r["id"], reverse=True)
    return runs


def build(out_dir):
    runs = _collect_runs()
    runs_dir = os.path.join(out_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    catalog_runs = []
    for r in runs:
        sid = _safe(r["id"])
        detail = r  # the full object is the detail file
        with open(os.path.join(runs_dir, "%s.json" % sid), "w", encoding="utf-8") as f:
            json.dump(detail, f)
        catalog_runs.append({
            "id": r["id"], "safe_id": sid, "type": r["type"], "source": r.get("source"),
            "arms": r.get("arms"), "contrast": r.get("contrast"), "verdict": r.get("verdict"),
            "overall": r.get("overall"), "has_moves": r.get("has_moves", False),
            "has_atoms": r.get("has_atoms", False), "batch": r.get("batch"), "seed": r.get("seed"),
            "detail": "runs/%s.json" % sid,
        })
    # committed sample snapshot — guarantees the AtomSpace page has content on a fresh checkout
    sample = None
    sp = os.path.join(_FREECIV, "samples", "atomspace_snapshot_turn1.json")
    if os.path.isfile(sp):
        try:
            sample = json.load(open(sp, encoding="utf-8"))
        except (ValueError, OSError):
            sample = None
    return {"generated": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "runs": catalog_runs, "batches": _batches(), "fixtures": _fixtures(),
            "sample_atomspace": sample}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(_HERE, "public", "data"))
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    catalog = build(args.out_dir)
    with open(os.path.join(args.out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
    n_moves = sum(1 for r in catalog["runs"] if r.get("has_moves"))
    n_atoms = sum(1 for r in catalog["runs"] if r.get("has_atoms"))
    print("wrote %s — %d run(s) [%d moves, %d atoms], %d batch(es), %d fixture set(s)" %
          (os.path.join(args.out_dir, "index.json"), len(catalog["runs"]), n_moves, n_atoms,
           len(catalog["batches"]), len(catalog["fixtures"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
