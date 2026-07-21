#!/usr/bin/env bash
# Launch the PLN-vs-plain-LLM A/B run (Issue #25 experiment): two in-container arms in parallel.
#
# Both arms use the SAME model/provider (SNET via env), seed, nation, and validation; only the state
# representation differs (pln = plain facts + MeTTa/PLN recommendations; plain = plain facts only).
# The worktree is mounted OVER the baked repo so the container runs live code and MeTTa library
# imports resolve; --network host lets the container reach the freeciv stack on localhost:8002.
#
# Usage: bash benchmarks/freeciv/ab_run.sh [SEED] [HOURS] [MAX_TURNS]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"          # worktree root
cd "$REPO"

# LLM provider through the env (SNET_API_KEY etc.)
set -a; . ./.env; set +a
: "${SNET_API_KEY:?SNET_API_KEY not set in .env}"

# This image's PeTTa build has no `git-import!`, so reason.py's default (library OmegaClaw-Core …)
# imports silently resolve to nothing and lib_pln never loads — the v1 PLN arm would derive 0
# conclusions. Import the reasoning libs + rules by their real in-container paths instead, so the
# v1 arm actually fires. (The v2 arm reasons via reason_v2/chain.py in pure Python, so it does not
# depend on this.) Override OMEGACLAW_REASON_IMPORTS in the environment to change it.
export OMEGACLAW_REASON_IMPORTS="${OMEGACLAW_REASON_IMPORTS:-$(printf '%s\n' \
  '!(import! &self "repos/OmegaClaw-Core/core/lib_nal.metta")' \
  '!(import! &self "repos/OmegaClaw-Core/core/lib_pln.metta")' \
  '!(import! &self "repos/OmegaClaw-Core/benchmarks/freeciv/rules.metta")')}"

SEED="${1:-42}"; HOURS="${2:-10}"; MAX_TURNS="${3:-2000}"
IMAGE="${OMEGACLAW_IMAGE:-omegaclaw:local}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_HOST="$REPO/benchmarks/freeciv/ab_runs/$TS"
OUT_CTR="/PeTTa/repos/OmegaClaw-Core/benchmarks/freeciv/ab_runs/$TS"
mkdir -p "$OUT_HOST"
echo "run dir: $OUT_HOST   seed=$SEED hours=$HOURS max_turns=$MAX_TURNS image=$IMAGE"

launch () {  # label arm game_id  (label is the container/game tag; arm is the ab_sim --arm value)
  local label="$1" arm="$2" gid="$3"
  docker run -d --name "fc-ab-${label}-${TS}" --network host \
    --entrypoint bash \
    -v "$REPO":/PeTTa/repos/OmegaClaw-Core \
    -e SNET_API_KEY -e FREECIV_PROVIDER="${FREECIV_PROVIDER:-SNET}" \
    -e FREECIV_PROXY_WS="ws://localhost:8002/llmsocket/8002" \
    -e OMEGACLAW_METTA_CMD -e OMEGACLAW_METTA_CWD -e OMEGACLAW_REASON_IMPORTS -e OMEGACLAW_V2_DIR \
    "$IMAGE" -lc "pip install --break-system-packages -q websockets >/dev/null 2>&1; \
      exec python3 /PeTTa/repos/OmegaClaw-Core/benchmarks/freeciv/ab_sim.py \
        --arm '${arm}' --game-id ${gid} --seed ${SEED} --hours ${HOURS} \
        --max-turns ${MAX_TURNS} --out ${OUT_CTR}"
  echo "launched label=${label} arm=${arm} container=fc-ab-${label}-${TS}"
}

# ARMS_TO_RUN: space-separated "label:arm" pairs. Default is the full 3-arm experiment so the
# reporters' PRIMARY contrast (facts+chaining vs facts-only — the marginal value of chaining,
# holding the fact-proposal call constant) is actually produced by a plain single run. The v2
# atomspace arm is opt-in (it needs the v2 scratch dir), e.g.:
#   ARMS_TO_RUN="fc:facts+chaining fo:facts-only plain:plain v2:facts+chaining-v2" bash ab_run.sh
ARMS_TO_RUN="${ARMS_TO_RUN:-fc:facts+chaining fo:facts-only plain:plain}"
for pair in $ARMS_TO_RUN; do
  launch "${pair%%:*}" "${pair#*:}" "ab_${pair%%:*}_${TS}"
done

echo "$OUT_HOST" > "$REPO/benchmarks/freeciv/ab_runs/LATEST"
echo
echo "Progress:  python3 benchmarks/freeciv/ab_report.py $OUT_HOST"
echo "Final:     python3 benchmarks/freeciv/ab_report.py $OUT_HOST --final"
echo "Logs:      docker logs -f fc-ab-<label>-${TS}   (labels: ${ARMS_TO_RUN})"
