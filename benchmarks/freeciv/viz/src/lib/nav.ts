import { useSearchParams } from "react-router-dom";

// Selection lives in the URL query so every page shares it and deep-links work:
//   ?run=<safe_id>&game=<idx>&turn=<n>&arm=<name>
export function useSelection() {
  const [sp, setSp] = useSearchParams();
  const runId = sp.get("run");
  const game = parseInt(sp.get("game") ?? "0", 10) || 0;
  const turn = sp.get("turn") ? parseInt(sp.get("turn")!, 10) : null;
  const arm = sp.get("arm");

  function set(patch: Record<string, string | number | null>) {
    const next = new URLSearchParams(sp);
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, String(v));
    }
    setSp(next, { replace: true });
  }
  return { runId, game, turn, arm, set };
}

// Build a link to another page preserving the current selection.
export function withSelection(path: string, sp: URLSearchParams): string {
  const q = sp.toString();
  return q ? `${path}?${q}` : path;
}
