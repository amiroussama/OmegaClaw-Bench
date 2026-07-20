"""Aggregate a PLN-vs-LLM batch into statistics (works on partial/in-progress batches).

Scans <batch_dir>/seed*/ for:
  duel/g1/duel.jsonl, duel/g2/duel.jsonl   (mirror pair; g1 PLN=side0, g2 PLN=side1)
  ab/pln.jsonl, ab/plain.jsonl             (A/B arms)

For every completed game it takes the FINAL per-side metrics (last record with metrics), decides the
territory winner (cities > units > techs, matching the reporters), and collects per-game pln-minus-
plain deltas. Reports, per experiment: N games, PLN win/loss/tie counts, an exact two-sided sign-test
p-value (binomial over non-ties), and per-metric mean delta with a paired t-stat + normal-approx
two-sided p. Writes <batch_dir>/aggregate.{md,json}. Stdlib only.

Usage: python3 benchmarks/freeciv/batch/aggregate.py <batch_dir>
"""
import glob
import json
import math
import os
import sys

_FREECIV = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # benchmarks/freeciv
if _FREECIV not in sys.path:
    sys.path.insert(0, _FREECIV)
import metrics as _metrics  # noqa: E402

METRICS = ("n_cities", "n_units", "n_techs")
ERA_THRESHOLDS = ("4", "6")  # tech-count thresholds aggregated as era-progression deltas


def _rows(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                pass
    return out


def _duel_final(path, pln_side):
    """Final (pln_metrics, plain_metrics) from a duel game, or None."""
    last = None
    for r in _rows(path):
        s0, s1 = r.get("side0"), r.get("side1")
        if isinstance(s0, dict) and isinstance(s1, dict) and s0.get("metrics") and s1.get("metrics"):
            last = r
    if not last:
        return None
    m = {0: last["side0"]["metrics"], 1: last["side1"]["metrics"]}
    return m[pln_side], m[1 - pln_side]


def _ab_final(path):
    last = None
    for r in _rows(path):
        if isinstance(r.get("metrics"), dict) and r["metrics"].get("n_cities") is not None:
            last = r
    return last["metrics"] if last else None


def _duel_series(path, pln_side):
    """(pln_traj, plain_traj, pln_bundles) from a duel game for era + PLN-quality (or None)."""
    pln_traj, plain_traj, bundles = [], [], []
    for r in _rows(path):
        s0, s1 = r.get("side0"), r.get("side1")
        if not (isinstance(s0, dict) and isinstance(s1, dict) and s0.get("metrics") and s1.get("metrics")):
            continue
        pln_s, plain_s = (s0, s1) if pln_side == 0 else (s1, s0)
        turn = r.get("turn")
        pln_traj.append({"turn": turn, **pln_s["metrics"]})
        plain_traj.append({"turn": turn, **plain_s["metrics"]})
        bundles.append({"moves": pln_s.get("moves") or [],
                        "recommendations": pln_s.get("recommendations") or []})
    return (pln_traj, plain_traj, bundles) if pln_traj else None


def _ab_series(path):
    """(traj, bundles) from an A/B arm for era + PLN-quality."""
    traj, bundles = [], []
    for r in _rows(path):
        m = r.get("metrics")
        if isinstance(m, dict) and m.get("n_cities") is not None:
            traj.append({"turn": r.get("advanced_to") or r.get("turn"), **m})
            bundles.append({"moves": r.get("moves") or [],
                            "recommendations": r.get("recommendations") or []})
    return traj, bundles


def _era_delta(era_pairs):
    """Paired plain-minus-pln turns-to-N deltas (positive favors PLN — reaches N sooner).

    ``era_pairs``: list of (pln_t2t, plain_t2t) dicts. Censored pairs (either None) are skipped;
    n (in the paired-t block) reports how many decisive pairs remained.
    """
    out = {}
    for n in ERA_THRESHOLDS:
        diffs = [plain[n] - pln[n] for pln, plain in era_pairs
                 if pln.get(n) is not None and plain.get(n) is not None]
        out[n] = _paired_t(diffs)
    return out


def _quality_means(quality_list):
    def _mean(key):
        xs = [q[key] for q in quality_list if isinstance(q.get(key), (int, float))]
        return round(sum(xs) / len(xs), 4) if xs else None
    return {"n": len(quality_list),
            "mean_pln_action_success_rate": _mean("pln_action_success_rate"),
            "mean_rec_adoption_rate": _mean("rec_adoption_rate")}


def _winner(pln, plain):
    for k in METRICS:
        pv, qv = pln.get(k) or 0, plain.get(k) or 0
        if pv != qv:
            return "pln" if pv > qv else "plain"
    return "tie"


def _binom_two_sided(k, n):
    """Exact two-sided sign-test p for k successes in n fair Bernoulli trials."""
    if n == 0:
        return 1.0
    def pmf(i):
        return math.comb(n, i) * 0.5 ** n
    obs = pmf(k)
    return min(1.0, sum(pmf(i) for i in range(n + 1) if pmf(i) <= obs + 1e-12))


def _paired_t(diffs):
    n = len(diffs)
    if n < 2:
        return {"n": n, "mean": (diffs[0] if diffs else None), "t": None, "p_approx": None}
    mean = sum(diffs) / n
    var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return {"n": n, "mean": round(mean, 3), "sd": 0.0, "t": None,
                "p_approx": (0.0 if mean != 0 else 1.0)}
    t = mean / (sd / math.sqrt(n))
    p = math.erfc(abs(t) / math.sqrt(2))  # normal approximation to the two-sided t p-value
    return {"n": n, "mean": round(mean, 3), "sd": round(sd, 3), "t": round(t, 3),
            "p_approx": round(p, 4)}


def _summarize(games, label):
    """games: list of (pln_metrics, plain_metrics)."""
    wins = {"pln": 0, "plain": 0, "tie": 0}
    deltas = {k: [] for k in METRICS}
    for pln, plain in games:
        wins[_winner(pln, plain)] += 1
        for k in METRICS:
            deltas[k].append((pln.get(k) or 0) - (plain.get(k) or 0))
    decisive = wins["pln"] + wins["plain"]
    return {
        "label": label,
        "n_games": len(games),
        "wins": wins,
        "sign_test_p": round(_binom_two_sided(wins["pln"], decisive), 4) if decisive else None,
        "deltas_pln_minus_plain": {k: _paired_t(deltas[k]) for k in METRICS},
    }


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: aggregate.py <batch_dir>")
    base = sys.argv[1]
    if not os.path.isabs(base):
        base = os.path.join(os.getcwd(), base)

    duel_games, ab_games, per_seed = [], [], []
    duel_era, duel_quality, ab_era, ab_quality = [], [], [], []
    for sd in sorted(glob.glob(os.path.join(base, "seed*"))):
        seed = os.path.basename(sd).replace("seed", "")
        row = {"seed": seed}
        g1 = _duel_final(os.path.join(sd, "duel", "g1", "duel.jsonl"), 0)
        g2 = _duel_final(os.path.join(sd, "duel", "g2", "duel.jsonl"), 1)
        for tag, g in (("duel_g1", g1), ("duel_g2", g2)):
            if g:
                duel_games.append(g)
                row[tag] = _winner(*g)
        for path, pln_side in ((os.path.join(sd, "duel", "g1", "duel.jsonl"), 0),
                               (os.path.join(sd, "duel", "g2", "duel.jsonl"), 1)):
            series = _duel_series(path, pln_side)
            if series:
                pln_traj, plain_traj, bundles = series
                duel_era.append((_metrics.turns_to_tech_counts(pln_traj),
                                 _metrics.turns_to_tech_counts(plain_traj)))
                duel_quality.append(_metrics.pln_quality(bundles))
        abp = _ab_final(os.path.join(sd, "ab", "pln.jsonl"))
        abq = _ab_final(os.path.join(sd, "ab", "plain.jsonl"))
        if abp and abq:
            ab_games.append((abp, abq))
            row["ab"] = _winner(abp, abq)
        pln_traj, pln_bundles = _ab_series(os.path.join(sd, "ab", "pln.jsonl"))
        plain_traj, _ = _ab_series(os.path.join(sd, "ab", "plain.jsonl"))
        if pln_traj and plain_traj:
            ab_era.append((_metrics.turns_to_tech_counts(pln_traj),
                           _metrics.turns_to_tech_counts(plain_traj)))
            ab_quality.append(_metrics.pln_quality(pln_bundles))
        per_seed.append(row)

    duel_sum = _summarize(duel_games, "duel (mirror slots, PLN vs plain)")
    duel_sum["era_delta_turns_to_tech"] = _era_delta(duel_era)
    duel_sum["pln_quality"] = _quality_means(duel_quality)
    ab_sum = _summarize(ab_games, "A/B (PLN vs plain, each vs AI)")
    ab_sum["era_delta_turns_to_tech"] = _era_delta(ab_era)
    ab_sum["pln_quality"] = _quality_means(ab_quality)

    result = {
        "batch": base,
        "seeds_scanned": len(per_seed),
        "duel": duel_sum,
        "ab": ab_sum,
        "per_seed": per_seed,
    }
    with open(os.path.join(base, "aggregate.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    lines = ["# PLN-vs-LLM batch — statistical aggregate", "",
             "batch: %s" % base, "seeds scanned: %d" % len(per_seed), ""]
    for exp in ("duel", "ab"):
        s = result[exp]
        w = s["wins"]
        lines += ["## %s" % s["label"],
                  "games: %d  |  PLN wins: %d, plain wins: %d, ties: %d  |  sign-test p=%s"
                  % (s["n_games"], w["pln"], w["plain"], w["tie"], s["sign_test_p"]),
                  "", "| metric | mean Δ (pln−plain) | n | t | p≈ |",
                  "|---|---|---|---|---|"]
        for k in METRICS:
            d = s["deltas_pln_minus_plain"][k]
            lines.append("| %s | %s | %s | %s | %s |"
                         % (k.replace("n_", ""), d.get("mean"), d.get("n"), d.get("t"), d.get("p_approx")))
        lines.append("")
        # era progression (turns to reach N techs; positive Δ favors PLN — reaches N sooner)
        era = s.get("era_delta_turns_to_tech", {})
        lines += ["Era progression — Δ turns to reach N techs (plain−pln; positive favors PLN):",
                  "", "| N techs | mean Δ | pairs | t | p≈ |", "|---|---|---|---|---|"]
        for n in ERA_THRESHOLDS:
            d = era.get(n, {})
            lines.append("| %s | %s | %s | %s | %s |"
                         % (n, d.get("mean"), d.get("n"), d.get("t"), d.get("p_approx")))
        q = s.get("pln_quality", {})
        lines += ["", "PLN recommendation quality (mean over %s runs): action success rate=%s, "
                  "rec adoption rate=%s" % (q.get("n"), q.get("mean_pln_action_success_rate"),
                                            q.get("mean_rec_adoption_rate")), ""]
    lines += ["_Sign-test p: exact two-sided binomial over decisive games. "
              "Metric p≈: normal approximation to the paired-t two-sided p (use with care for small n). "
              "Era Δ skips censored pairs (a side that never reached N techs)._"]
    md = "\n".join(lines)
    with open(os.path.join(base, "aggregate.md"), "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
