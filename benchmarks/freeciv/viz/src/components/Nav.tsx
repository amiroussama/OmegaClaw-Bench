import { NavLink, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/atoms", label: "AtomSpace" },
  { to: "/reasoning", label: "Reasoning" },
  { to: "/ab", label: "A/B run" },
  { to: "/batch", label: "Batch" },
];

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState<string>(
    () => document.documentElement.getAttribute("data-theme") || "light"
  );
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("fcviz-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

export default function Nav() {
  const [theme, toggle] = useTheme();
  const loc = useLocation();
  // preserve ?run=…&game=… selection across page switches
  const q = loc.search;
  return (
    <header className="topnav">
      <div className="brand">
        <span className="dotmark" />
        FreeCiv&nbsp;PLN
      </div>
      <nav>
        {LINKS.map((l) => (
          <NavLink key={l.to} to={{ pathname: l.to, search: q }} end={l.end}
            className={({ isActive }) => (isActive ? "active" : "")}>
            {l.label}
          </NavLink>
        ))}
      </nav>
      <div className="spacer" />
      <button className="iconbtn" onClick={toggle} title="Toggle theme">
        {theme === "dark" ? "☀ Light" : "☾ Dark"}
      </button>
    </header>
  );
}
