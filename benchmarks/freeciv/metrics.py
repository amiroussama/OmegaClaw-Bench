"""Per-turn game metrics extracted from a normalized FreeCiv state (Issue #25 A/B experiment)
plus era-progression trajectory helpers (Issue #5).

Pure functions of the normalized state / a list of per-turn records, so everything is
deterministic and host-testable. Used to build the per-turn trajectory both arms are compared on.

Era note: FreeCiv has no Civ-style "eras" and the proxy state carries no era field, so
"era progression" is measured as tech-milestone progression — how fast a player reaches N
researched techs (primary) and named milestone techs (secondary, best-effort). See
``docs/benchmark-protocols.md``.
"""

# Tech-count thresholds used as the primary era-progression proxy (turns to reach N techs).
TECH_THRESHOLDS = (2, 4, 6, 8)
# Named milestone techs (secondary, best-effort — depends on the proxy exposing tech names).
MILESTONE_TECHS = ("Bronze Working", "Currency", "Writing", "Monarchy")


def _num(x):
    return x if isinstance(x, (int, float)) else None


def _player(norm, pid):
    """The perspective player's dict from the normalized players list ({} if absent)."""
    for p in norm.get("players", []):
        if isinstance(p, dict) and p.get("id") == pid:
            return p
    return {}


def _researched_tech_names(norm):
    """Sorted researched-tech names for the perspective player (summary block or raw techs dict).

    Mirrors adapter._researched_techs but kept local so metrics.py stays adapter-independent.
    """
    pid = norm.get("player_perspective")
    strat = norm.get("strategic") or {}
    tp = strat.get("tech_position") if isinstance(strat.get("tech_position"), dict) else {}
    if isinstance(tp.get("researched"), list):
        return sorted(str(t) for t in tp["researched"])
    techs = norm.get("techs") or {}
    if isinstance(techs, dict):
        val = techs.get("player{}".format(pid))
        if isinstance(val, list):
            return sorted(str(t) for t in val)
    if isinstance(techs, list):
        return sorted(str(t) for t in techs)
    return []


def metrics_from_state(norm):
    """Return the comparison metrics for a normalized state.

    {turn, score, gold, science, n_cities, n_units, n_techs, tech_names}. Missing values -> None/0.

    gold/score are read from the per-player block first (the runtime shape carries the real
    values there; the documented economic/strategic blocks are often zero — see
    docs/benchmark-protocols.md "Known limits"), falling back to the summary blocks.
    """
    pid = norm.get("player_perspective")
    player = _player(norm, pid)

    econ = norm.get("economic") or {}
    res = econ.get("resources") if isinstance(econ.get("resources"), dict) else econ
    strat = norm.get("strategic") or {}
    vp = strat.get("victory_progress") if isinstance(strat.get("victory_progress"), dict) else {}
    tp = strat.get("tech_position") if isinstance(strat.get("tech_position"), dict) else {}

    # gold: per-player block preferred, then economic.resources.gold / economic.gold
    gold = _num(player.get("gold"))
    if gold is None and isinstance(res, dict):
        gold = _num(res.get("gold"))

    # score: per-player (only when >= 0; AI players report -1 = unknown), then victory_progress / strategic
    pscore = _num(player.get("score"))
    if pscore is not None and pscore >= 0:
        score = pscore
    else:
        score = _num(vp.get("current_score", strat.get("score")))

    # science: economic.resources.science / research, then strategic.tech_position.research_points
    science = _num(res.get("science", res.get("research"))) if isinstance(res, dict) else None
    if science is None:
        science = _num(tp.get("research_points"))

    n_cities = sum(1 for c in norm.get("cities", []) if c.get("owner") == pid)
    n_units = sum(1 for u in norm.get("units", []) if u.get("owner") == pid)

    tech_names = _researched_tech_names(norm)
    n_techs = len(tech_names)

    turn = norm.get("turn")
    try:
        turn = int(turn) if turn is not None else None
    except (TypeError, ValueError):
        pass

    return {"turn": turn, "score": score, "gold": gold, "science": science,
            "n_cities": n_cities, "n_units": n_units, "n_techs": n_techs,
            "tech_names": tech_names}


# --------------------------------------------------------------------------- era progression

def _traj_rows(traj):
    """Records with a usable numeric turn, sorted ascending by turn."""
    rows = [r for r in (traj or []) if isinstance(r, dict) and isinstance(r.get("turn"), (int, float))]
    return sorted(rows, key=lambda r: r["turn"])


def turns_to_tech_counts(traj, thresholds=TECH_THRESHOLDS):
    """First turn at which n_techs >= N, per threshold N. None means never reached (censored).

    ``traj`` is an iterable of per-turn records carrying ``turn`` and ``n_techs``.
    """
    rows = _traj_rows(traj)
    out = {}
    for n in thresholds:
        hit = None
        for r in rows:
            if (r.get("n_techs") or 0) >= n:
                hit = int(r["turn"])
                break
        out[str(n)] = hit
    return out


def turns_to_milestones(traj, milestones=MILESTONE_TECHS):
    """First turn a named milestone tech appears in ``tech_names``. None means never (censored).

    Records lacking ``tech_names`` (older runs) simply don't contribute — best-effort.
    """
    rows = _traj_rows(traj)
    out = {m: None for m in milestones}
    for r in rows:
        names = r.get("tech_names") or []
        for m in milestones:
            if out[m] is None and m in names:
                out[m] = int(r["turn"])
    return out


def era_progression(traj):
    """Era-progression block for a per-turn trajectory.

    {turns_to_tech_count: {N: turn|None}, turns_to_milestone: {name: turn|None},
     tech_rate: techs-per-turn over the run (final n_techs / final turn), or None}.
    """
    rows = _traj_rows(traj)
    last = rows[-1] if rows else {}
    last_turn = int(last.get("turn") or 0)
    last_techs = int(last.get("n_techs") or 0)
    return {
        "turns_to_tech_count": turns_to_tech_counts(traj),
        "turns_to_milestone": turns_to_milestones(traj),
        "tech_rate": round(last_techs / last_turn, 4) if last_turn else None,
    }


# --------------------------------------------------------------------------- PLN action quality

# actor_kind (as logged in per-move records) -> recommendation entity token prefix.
_ACTOR_PREFIX = {"unit_id": "Unit", "city_id": "City", "tech_id": "Tech"}


def move_entity(mv):
    """Recommendation-entity token for a per-move record, e.g. Unit_102 (None if unmappable)."""
    prefix = _ACTOR_PREFIX.get(mv.get("actor_kind"))
    if prefix is None or mv.get("actor") is None:
        return None
    return "{}_{}".format(prefix, mv["actor"])


def pln_quality(turn_bundles):
    """PLN recommendation-quality metrics over per-turn move/recommendation bundles.

    ``turn_bundles`` is an iterable of dicts with ``moves`` (per-move records carrying
    ``pln_recommended`` and ``valid``) and ``recommendations`` ([{entity, action}]).

    - pln_action_success_rate = valid PLN-recommended moves / all PLN-recommended moves
      (did acting on a recommendation produce a legal action?). None if no such moves.
    - rec_adoption_rate = per turn with >=1 recommendation, the fraction of recommendations
      whose entity was the actor of >=1 proposed move, averaged over those turns. None if none.
    """
    total = valid = 0
    adoption = []
    for b in turn_bundles:
        moves = b.get("moves") or []
        for mv in moves:
            if mv.get("pln_recommended"):
                total += 1
                if mv.get("valid"):
                    valid += 1
        recs = b.get("recommendations") or []
        if recs:
            ents = {move_entity(mv) for mv in moves}
            ents.discard(None)
            adopted = sum(1 for rc in recs if rc.get("entity") in ents)
            adoption.append(adopted / len(recs))
    return {
        "pln_rec_proposed": total,
        "pln_rec_valid": valid,
        "pln_action_success_rate": round(valid / total, 4) if total else None,
        "rec_adoption_rate": round(sum(adoption) / len(adoption), 4) if adoption else None,
    }
