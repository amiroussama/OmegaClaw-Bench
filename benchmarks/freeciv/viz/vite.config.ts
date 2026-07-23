import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" keeps asset URLs relative so the built dist/ works when served
// by `python3 -m http.server` from any path (serve.sh prod mode).
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 8009, strictPort: false },
  build: { outDir: "dist", emptyOutDir: true },
});
