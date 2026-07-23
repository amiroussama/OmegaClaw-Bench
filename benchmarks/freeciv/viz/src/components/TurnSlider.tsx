// A turn selector over an explicit list of available turns (range slider + readout).
export default function TurnSlider({
  turns,
  value,
  onChange,
}: {
  turns: number[];
  value: number;
  onChange: (t: number) => void;
}) {
  if (!turns.length) return null;
  const idx = Math.max(0, turns.indexOf(value));
  return (
    <label className="ctl">
      Turn <b className="tnum" style={{ color: "var(--ink)" }}>{turns[idx]}</b>{" "}
      <span className="muted">({idx + 1}/{turns.length})</span>
      <input
        type="range"
        min={0}
        max={turns.length - 1}
        value={idx}
        onChange={(e) => onChange(turns[parseInt(e.target.value, 10)])}
      />
    </label>
  );
}
