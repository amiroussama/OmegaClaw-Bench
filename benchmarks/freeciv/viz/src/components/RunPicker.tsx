import type { Catalog, RunCatalogEntry } from "../lib/schema";
import { useSelection } from "../lib/nav";

// Run selector shared by the run-scoped pages. `filter` narrows to ab/duel/atoms-bearing.
export default function RunPicker({
  catalog,
  filter = "any",
  gameCount,
}: {
  catalog: Catalog;
  filter?: "any" | "ab" | "duel" | "atoms" | "moves";
  gameCount?: number;
}) {
  const { runId, game, set } = useSelection();
  let runs = catalog.runs;
  if (filter === "ab") runs = runs.filter((r) => r.type === "ab");
  else if (filter === "duel") runs = runs.filter((r) => r.type === "duel");
  else if (filter === "atoms") runs = runs.filter((r) => r.has_atoms);
  else if (filter === "moves") runs = runs.filter((r) => r.has_moves);

  const current = runs.find((r) => r.safe_id === runId) ?? runs[0];

  return (
    <div className="controls">
      <label className="ctl">
        Run
        <select
          value={current?.safe_id ?? ""}
          onChange={(e) => set({ run: e.target.value, game: 0, turn: null })}
        >
          {runs.map((r) => (
            <option key={r.safe_id} value={r.safe_id}>
              {label(r)}
            </option>
          ))}
        </select>
      </label>
      {gameCount && gameCount > 1 && (
        <label className="ctl">
          Game
          <select value={game} onChange={(e) => set({ game: parseInt(e.target.value, 10), turn: null })}>
            {Array.from({ length: gameCount }, (_, i) => (
              <option key={i} value={i}>
                g{i + 1}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

function label(r: RunCatalogEntry): string {
  const tag = r.type === "duel" ? "⚔ duel" : "⇄ A/B";
  return `${tag} · ${r.id}`;
}

export function currentRun(
  catalog: Catalog,
  runId: string | null,
  filter: "any" | "ab" | "duel" | "atoms" | "moves" = "any"
) {
  let runs = catalog.runs;
  if (filter === "ab") runs = runs.filter((r) => r.type === "ab");
  else if (filter === "duel") runs = runs.filter((r) => r.type === "duel");
  else if (filter === "atoms") runs = runs.filter((r) => r.has_atoms);
  else if (filter === "moves") runs = runs.filter((r) => r.has_moves);
  return runs.find((r) => r.safe_id === runId) ?? runs[0] ?? null;
}
