import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: the backend (FastAPI) runs on :8000 and owns both the JSON API
// (/api) and the static media tree (/media). In production the backend serves
// the built `dist/` directly, so the proxy only matters during `npm run dev`.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/media": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
