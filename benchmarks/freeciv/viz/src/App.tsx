import { Routes, Route } from "react-router-dom";
import Nav from "./components/Nav";
import Overview from "./pages/Overview";
import Atoms from "./pages/Atoms";
import Reasoning from "./pages/Reasoning";
import AbRun from "./pages/AbRun";
import Batch from "./pages/Batch";

export default function App() {
  return (
    <div className="app">
      <Nav />
      <main>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/atoms" element={<Atoms />} />
          <Route path="/reasoning" element={<Reasoning />} />
          <Route path="/ab" element={<AbRun />} />
          <Route path="/batch" element={<Batch />} />
          <Route path="*" element={<Overview />} />
        </Routes>
      </main>
    </div>
  );
}
