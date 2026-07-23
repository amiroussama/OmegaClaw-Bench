// One normalizer for the two truth-value shapes: AtomSpace snapshots use {f,c},
// PLN traces use {strength,confidence}. Everything downstream sees {s, c}.

export interface NormStv {
  s: number;
  c: number;
}

export function normStv(
  x: { f: number; c: number } | { strength: number; confidence: number } | null | undefined
): NormStv | null {
  if (!x) return null;
  if ("f" in x && typeof x.f === "number") return { s: x.f, c: x.c };
  if ("strength" in x && typeof x.strength === "number") return { s: x.strength, c: x.confidence };
  return null;
}

export function fmtStv(
  x: { f: number; c: number } | { strength: number; confidence: number } | null | undefined
): string {
  const n = normStv(x);
  if (!n) return "—";
  return `stv ${round(n.s, 3)} / ${round(n.c, 3)}`;
}

export function round(v: number, d = 2): number {
  const m = Math.pow(10, d);
  return Math.round(v * m) / m;
}
