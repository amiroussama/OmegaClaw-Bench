import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import "./theme.css";
import "./design/app.css";
import "./design/inspect.css";
import App from "./App";

// HashRouter: the app is served by a static file server (no route rewriting),
// so client routes live under #/… and relative data fetches resolve off index.html.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>
);
