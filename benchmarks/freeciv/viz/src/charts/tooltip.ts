// A single reused fixed-position tooltip element (one per document), controlled
// imperatively by the SVG charts.

let el: HTMLDivElement | null = null;

function node(): HTMLDivElement {
  if (!el) {
    el = document.createElement("div");
    el.className = "tooltip";
    document.body.appendChild(el);
  }
  return el;
}

export function showTip(html: string, x: number, y: number) {
  const t = node();
  t.innerHTML = html;
  t.style.opacity = "1";
  // place near cursor, flipping to stay on-screen
  const pad = 14;
  const w = t.offsetWidth || 180;
  const left = x + pad + w > window.innerWidth ? x - pad - w : x + pad;
  t.style.left = `${Math.max(4, left)}px`;
  t.style.top = `${y + pad}px`;
}

export function hideTip() {
  if (el) el.style.opacity = "0";
}
