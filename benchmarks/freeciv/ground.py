"""Ground abstract PLN recommendations into concrete, LEGAL FreeCiv actions.

PLN stays abstract: ``reason.derive`` emits ``(Recommend <entity> <action>)`` atoms like
``(Recommend City_1 Defend)`` or ``(Recommend Unit_301 Settle)``. Those are too vague for the
agent to act on precisely (the 20-seed batch saw only ~8% action/recommendation uptake), so this
deterministic step maps each abstract recommendation to a specific action from the CURRENT state —
e.g. Defend → the nearest idle owned unit fortifies on / moves toward the city; Settle → the
settler founds a city; Food → a worker irrigates.

Every grounded action is re-checked with ``actions.validate_action`` so ONLY legal suggestions
surface (0%-illegal invariant preserved). Grounding is a pure function of the recommendation + the
normalized state; it returns ``None`` when nothing legal fits (the caller falls back to the
abstract hint).
"""

import re

from . import actions

# (Recommend <entity> <action>) with concrete (non-$) entity/action tokens.
_REC_RE = re.compile(r"\(Recommend\s+([A-Za-z0-9_]+)\s+([A-Za-z0-9_]+)\)")

# Recommendation verbs grouped by what they ground to.
_CITY_DEFEND = ("Defend", "BuildDefender", "Garrison")
_CITY_FOOD = ("Food", "Irrigate", "Grow")
_UNIT_SETTLE = ("Settle", "FoundCity", "Expand")
_UNIT_RETREAT = ("Retreat", "Flee")


def _split_entity(token):
    """'City_1' -> ('City', '1'); 'Unit_301' -> ('Unit', '301'); else (None, None)."""
    if "_" not in token:
        return None, None
    prefix, _, ident = token.partition("_")
    return prefix, ident


def _owned_units(norm):
    pid = norm.get("player_perspective")
    return [u for u in norm.get("units", [])
            if u.get("owner") == pid and u.get("x") is not None and u.get("y") is not None]


def _find(items, ident):
    for it in items:
        if str(it.get("id")) == str(ident):
            return it
    return None


def _is_settler(u):
    return str(u.get("type", "")).lower() in ("settlers", "settler", "migrants")


def _is_worker(u):
    return "work" in str(u.get("type", "")).lower() or "engineer" in str(u.get("type", "")).lower()


def _dist(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))  # Chebyshev (one tile = one step in FreeCiv)


def _nearest(units, x, y):
    return min(units, key=lambda u: _dist(u["x"], u["y"], x, y)) if units else None


def _step_toward(ux, uy, tx, ty):
    """One-tile step from (ux,uy) toward (tx,ty), clamped to +/-1 (the move-legality window)."""
    return ux + ((tx > ux) - (tx < ux)), uy + ((ty > uy) - (ty < uy))


def _legal(action, norm):
    """Return the action if it validates against the state, else None."""
    return action if actions.validate_action(action, norm).is_valid else None


def _ground_city_defense(city, norm):
    """Nearest owned unit → fortify on the city, else step toward it (prefer a non-settler)."""
    units = _owned_units(norm)
    cx, cy = city.get("x"), city.get("y")
    if cx is None or cy is None or not units:
        return None
    military = [u for u in units if not _is_settler(u) and not _is_worker(u)]
    unit = _nearest(military or units, cx, cy)
    if unit is None:
        return None
    if unit["x"] == cx and unit["y"] == cy:
        return _legal({"type": "unit_fortify", "unit_id": unit["id"]}, norm)
    dx, dy = _step_toward(unit["x"], unit["y"], cx, cy)
    return _legal({"type": "unit_move", "unit_id": unit["id"], "dest_x": dx, "dest_y": dy}, norm)


def _ground_city_food(city, norm):
    """Nearest owned worker → irrigate at its tile (falls back to None if no worker)."""
    workers = [u for u in _owned_units(norm) if _is_worker(u)]
    cx, cy = city.get("x"), city.get("y")
    worker = _nearest(workers, cx if cx is not None else 0, cy if cy is not None else 0)
    if worker is None:
        return None
    return _legal({"type": "unit_build_irrigation", "unit_id": worker["id"]}, norm)


def _ground_unit_settle(unit, norm):
    """A settler founds a city on its current tile."""
    if unit is None or not _is_settler(unit):
        return None
    return _legal({"type": "unit_build_city", "unit_id": unit["id"]}, norm)


def _ground_unit_retreat(unit, norm):
    """Step the unit one tile toward its owner's nearest city (best-effort safety)."""
    if unit is None:
        return None
    pid = norm.get("player_perspective")
    cities = [c for c in norm.get("cities", [])
              if c.get("owner") == pid and c.get("x") is not None and c.get("y") is not None]
    home = _nearest([{"x": c["x"], "y": c["y"], "id": c["id"]} for c in cities], unit["x"], unit["y"])
    if home is None:
        return None
    dx, dy = _step_toward(unit["x"], unit["y"], home["x"], home["y"])
    if (dx, dy) == (unit["x"], unit["y"]):
        return _legal({"type": "unit_fortify", "unit_id": unit["id"]}, norm)
    return _legal({"type": "unit_move", "unit_id": unit["id"], "dest_x": dx, "dest_y": dy}, norm)


def ground(rec, norm):
    """Map ``(Recommend <entity> <action>)`` to a concrete, LEGAL action dict, or None.

    Returns None when the recommendation is unparseable, the entity is missing/foreign, or no legal
    concrete action fits — the caller then keeps the abstract hint.
    """
    m = _REC_RE.search(rec or "")
    if not m:
        return None
    entity, action = m.group(1), m.group(2)
    kind, ident = _split_entity(entity)

    if action in _CITY_DEFEND or action in _CITY_FOOD:
        if kind != "City":
            return None
        city = _find(norm.get("cities", []), ident)
        if city is None or city.get("owner") != norm.get("player_perspective"):
            return None
        return _ground_city_defense(city, norm) if action in _CITY_DEFEND else _ground_city_food(city, norm)

    if action in _UNIT_SETTLE or action in _UNIT_RETREAT:
        if kind != "Unit":
            return None
        unit = _find(_owned_units(norm), ident)
        if unit is None:
            return None
        return _ground_unit_settle(unit, norm) if action in _UNIT_SETTLE else _ground_unit_retreat(unit, norm)

    return None


def format_action(action):
    """Compact human rendering of a grounded action for the prompt hint block."""
    if not action:
        return ""
    t = action.get("type", "?")
    if action.get("dest_x") is not None:
        return "%s unit %s -> (%s,%s)" % (t, action.get("unit_id"), action.get("dest_x"), action.get("dest_y"))
    if action.get("unit_id") is not None:
        return "%s unit %s" % (t, action.get("unit_id"))
    if action.get("city_id") is not None:
        return "%s city %s" % (t, action.get("city_id"))
    return t
