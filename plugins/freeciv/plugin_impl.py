"""FreeCiv plugin entrypoint (benchmarks<->core split).

Repackages the two FreeCiv agent tools — previously wired directly into OmegaClaw-Core's
`lib_omegaclaw.metta` / `skills.metta` — as a plugin loaded via the core `plugin_registry`.
Enable it by pointing `OMEGACLAW_PLUGINS_CONFIG_PATH` at this repo's `profile/plugins.yaml`
(which lists `plugins/freeciv` under `roots`). The agent then calls them as:

    plugin-invoke freeciv-observe ""
    plugin-invoke freeciv-action "{\"type\":\"end_turn\"}"

The heavy/deterministic logic still lives in `benchmarks/freeciv/` (the "producer stays
benchmark-local" decision); this entrypoint only puts that package on `sys.path` and wraps
`freeciv_tool.observe` / `freeciv_tool.act` as plugin tool handlers. `freeciv_tool` in turn
puts core `src/` (the git submodule) on `sys.path` for its lazy `metta_sessions` import.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # plugins/freeciv
# Walk up to the repo root (the dir that contains benchmarks/freeciv) and expose the freeciv
# package dir so `import freeciv_tool` resolves regardless of where the agent is launched from.
_root = _HERE
while _root != os.path.dirname(_root):
    if os.path.isdir(os.path.join(_root, "benchmarks", "freeciv")):
        break
    _root = os.path.dirname(_root)
_FREECIV = os.path.join(_root, "benchmarks", "freeciv")
if _FREECIV not in sys.path:
    sys.path.insert(0, _FREECIV)

import freeciv_tool  # noqa: E402  (freeciv_tool adds core/src to sys.path for metta_sessions)


def _observe(_arg=""):
    """freeciv-observe: fetch current game state as PLN premises. Takes no meaningful arg."""
    return freeciv_tool.observe()


def _action(arg):
    """freeciv-action: validate a candidate action (JSON string) and submit only if legal."""
    return freeciv_tool.act(arg)


def register():
    return [
        {"name": "freeciv-observe",
         "description": "Observe the current FreeCiv game state as PLN reasoning premises "
                        "(facts with (stv f c) truth values). No argument.",
         "arg": "input", "handler": _observe},
        {"name": "freeciv-action",
         "description": "Validate and submit a FreeCiv action given as a JSON string; illegal "
                        "moves are refused before submission.",
         "arg": "action_json", "handler": _action},
    ]
