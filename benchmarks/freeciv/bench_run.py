"""Single entry point selecting the benchmark protocol (Issue #5): A/B or duel.

    python3 benchmarks/freeciv/bench_run.py --mode ab   --arm pln --game-id g --out DIR [...]
    python3 benchmarks/freeciv/bench_run.py --mode duel --game-id g --pln-side 0 --out DIR [...]

This is a thin dispatcher: it strips ``--mode`` and forwards every remaining argument to
``ab_sim.main`` or ``duel_sim.main`` unchanged, so the two sims stay the single source of
truth for their own flags. See ``docs/benchmark-protocols.md`` for when to use which mode.
The standalone ``ab_sim.py`` / ``duel_sim.py`` (and ``ab_run.sh`` / ``duel_run.sh``) still work
directly; this wrapper just gives the batch harness and docs one mode-selecting command.
"""

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BENCH = os.path.dirname(_HERE)
if _BENCH not in sys.path:
    sys.path.insert(0, _BENCH)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--mode", choices=["ab", "duel"], required=True)
    ns, rest = ap.parse_known_args(argv)

    # forward the remaining args to the chosen sim's main() via sys.argv
    sys.argv = [sys.argv[0]] + rest
    if ns.mode == "ab":
        from freeciv import ab_sim
        return ab_sim.main()
    from freeciv import duel_sim
    return duel_sim.main()


if __name__ == "__main__":
    sys.exit(main())
