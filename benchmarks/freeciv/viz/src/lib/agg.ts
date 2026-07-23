import type { Aggregate, ContrastSummary } from "./schema";

// Ordered preference for the "primary" contrast to feature: the v2-vs-v1 comparison
// if present, else the 3-arm marginal-chaining contrast.
const PREFERRED = [
  "facts+chaining-v2_vs_facts+chaining",
  "facts+chaining_vs_facts-only",
  "facts+chaining_vs_plain",
];

export function primaryContrast(agg: Aggregate): ContrastSummary | null {
  const nonEmpty = (c?: ContrastSummary) => (c && c.n_games > 0 ? c : null);
  for (const k of PREFERRED) {
    const c = nonEmpty(agg.ab?.[k]);
    if (c) return c;
  }
  // fall back to any contrast with games
  for (const c of Object.values(agg.ab ?? {})) if (nonEmpty(c)) return c;
  return null;
}

export function contrastsWithGames(agg: Aggregate): ContrastSummary[] {
  const all = Object.values(agg.ab ?? {}).filter((c) => c.n_games > 0);
  // stable order: preferred first, then the rest
  all.sort((a, b) => rank(a) - rank(b));
  return all;
}
function rank(c: ContrastSummary): number {
  const key = `${c.a}_vs_${c.b}`;
  const i = PREFERRED.indexOf(key);
  return i === -1 ? 99 : i;
}

export const METRIC_LABELS: Record<string, string> = {
  n_cities: "cities",
  n_units: "units",
  n_techs: "techs",
  cities: "cities",
  units: "units",
  techs: "techs",
};
