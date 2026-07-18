# OmegaClaw-Bench

Benchmark, evaluation, and tooling suite extracted from
[OmegaClaw-Core](https://github.com/rojokaboti/OmegaClaw-Core) so the core stays lean. This
repo holds the KPI micro-benchmarks, the FreeCiv PLN-vs-LLM harness (sims, live play, viz),
the delegation feature, and the fork's design docs (`benchmark-docs/`).

## Layout

```
core/            git submodule -> OmegaClaw-Core (the code under test)
benchmarks/      KPI micro-benchmarks (one *_benchmark.py + *_fixtures.py per core feature)
benchmarks/freeciv/   FreeCiv adapter, sims (A/B, duel), live play, viz, samples
src/delegation.py     delegation feature (moved out of core)
Autotests/       moved tests: test_freeciv_*.py, test_delegation.py
plugins/freeciv/ FreeCiv tools repackaged as a core plugin (plugin.json + plugin_impl.py)
profile/plugins.yaml  enables the freeciv plugin (roots: [plugins/freeciv])
benchmark-docs/  the fork's design/eval docs (formerly rojo-docs/ in core)
```

## Setup

```bash
git submodule update --init          # fetch the core/ submodule
pip install -r core/requirements.txt # core deps (the benchmarks exercise core code)
pip install -r requirements.txt      # + websockets for FreeCiv live mode
```

The benchmark scripts add `core/src` (and `core/`) to `sys.path` automatically — each file
carries a small bootstrap that walks up to the submodule. No `PYTHONPATH` juggling needed.

## Run

```bash
python3 benchmarks/run_benchmark.py                 # KPI suite vs core/src
python3 benchmarks/freeciv/freeciv_tool.py          # FreeCiv offline self-test
( cd Autotests && python3 -m pytest -q )            # moved tests
```

## FreeCiv as a live-agent plugin

FreeCiv is no longer wired into core. To let a live OmegaClaw-Core agent play FreeCiv, launch
core with this repo's plugin config:

```bash
OMEGACLAW_PLUGINS_CONFIG_PATH=$PWD/profile/plugins.yaml \
FREECIV_PROXY_URL=... FREECIV_WS_URL=... FREECIV_API_TOKEN=... \
FREECIV_GAME_ID=... FREECIV_PLAYER_ID=... \
  <launch core>
```

The agent then calls `plugin-invoke freeciv-observe ""` and
`plugin-invoke freeciv-action "<json>"`. The plugin declares the `FREECIV_*` env vars as
requirements, so it stays a reported no-op until a live proxy is configured.

> Note: the plugin path carries the two FreeCiv *tools* but not the PLN `rules.metta` reasoning
> rules (the plugin mechanism loads tools + SKILL.md, not arbitrary `.metta`). The benchmark
> sims load `rules.metta` into their own MeTTa space and are unaffected. See
> `benchmark-docs/` for the FreeCiv design notes.

## Submodule pin

`core/` pins a specific OmegaClaw-Core commit. After the upstream `asi-alliance` sync lands in
core, bump the pin (`cd core && git pull && cd .. && git add core && git commit`) so the
benchmarks run against post-sync core.
