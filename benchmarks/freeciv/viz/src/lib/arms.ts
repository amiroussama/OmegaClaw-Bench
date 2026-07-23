// Arm identity -> CSS color token + label. Fixed categorical order (never cycled),
// matching the validated palette slots in theme.css.

export interface ArmStyle {
  key: string;
  label: string;
  short: string;
  cssVar: string; // CSS custom property carrying the validated hue
}

const ARMS: Record<string, ArmStyle> = {
  "facts+chaining": { key: "facts+chaining", label: "facts+chaining (v1 PLN)", short: "v1 PLN", cssVar: "--arm-chaining" },
  pln: { key: "pln", label: "facts+chaining (v1 PLN)", short: "v1 PLN", cssVar: "--arm-chaining" },
  "facts+chaining-v2": { key: "facts+chaining-v2", label: "facts+chaining-v2 (atomspace-v2)", short: "v2", cssVar: "--arm-v2" },
  "facts-only": { key: "facts-only", label: "facts-only (no PLN)", short: "facts-only", cssVar: "--arm-facts" },
  plain: { key: "plain", label: "plain (control)", short: "plain", cssVar: "--arm-plain" },
};

const FALLBACK: ArmStyle = { key: "?", label: "?", short: "?", cssVar: "--muted" };

export function armStyle(name: string | undefined | null): ArmStyle {
  if (!name) return FALLBACK;
  return ARMS[name] ?? { key: name, label: name, short: name, cssVar: "--muted" };
}

// Resolve a CSS var to its current computed hex (for inline SVG stroke/fill).
export function cssColor(cssVar: string): string {
  if (typeof document === "undefined") return "#888";
  const v = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim();
  return v || "#888";
}

// The pln/plain slots in a contrast map to the two contrast arms.
export function contrastArms(contrast?: string[]): [string, string] {
  if (contrast && contrast.length >= 2) return [contrast[0], contrast[contrast.length - 1]];
  return ["pln", "plain"];
}
