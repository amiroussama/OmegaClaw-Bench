"""FreeCiv auto-session seed test (relocated from core's test_metta_sessions.py during the
benchmarks<->core split). Verifies that `freeciv_tool.observe` seeds a metta_sessions session
with PLN premises and dedups on re-observe. Uses core `metta_sessions` (via the `core/`
submodule) plus the benchmark-local `freeciv_tool`.

Pure-Python; runs under pytest and standalone (`python3 Autotests/test_freeciv_session_seed.py`).
"""
import os
import sys
import tempfile

# Put the core submodule (metta_sessions) and the freeciv package (freeciv_tool) on sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(_ROOT, "core", "src"), os.path.join(_ROOT, "core"),
           os.path.join(_ROOT, "benchmarks", "freeciv")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import metta_sessions as ms  # noqa: E402
import freeciv_tool  # noqa: E402


def setup_function(_):
    ms.reset()


def test_freeciv_observe_seeds_session():
    with tempfile.TemporaryDirectory() as d:
        os.environ["OMEGACLAW_SESSION_SNAPSHOT_DIR"] = d
        os.environ["FREECIV_GAME_ID"] = "gtest"
        try:
            state = {"format": "llm_optimized", "turn": 2, "phase": "movement",
                     "player_perspective": 1,
                     "units": {"7": {"id": 7, "type": "Settler", "owner": 1, "x": 4, "y": 5, "hp": 10}},
                     "cities": {}, "players": {"1": {"id": 1}}, "techs": {"player1": ["Pottery"]},
                     "economic": {"resources": {"gold": 5}}, "strategic": {}, "tactical": {}}
            out = freeciv_tool.observe(state=state)
            assert "(stv" in out
            seeded = ms.facts("freeciv:gtest")
            assert seeded and all("(stv" in s for s in seeded)
            # re-observing the SAME state must not double the session (dedup)
            n1 = len(seeded)
            freeciv_tool.observe(state=state)
            n2 = len(ms.facts("freeciv:gtest"))
            assert n2 == n1, (n1, n2)
        finally:
            os.environ.pop("OMEGACLAW_SESSION_SNAPSHOT_DIR", None)
            os.environ.pop("FREECIV_GAME_ID", None)


if __name__ == "__main__":
    setup_function(None)
    test_freeciv_observe_seeds_session()
    print("ok: test_freeciv_observe_seeds_session")
