import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname } },
  server: {
    // The UI calls /api/...; Vite forwards it to FastAPI, so both share one origin and
    // no CORS is needed. In production nginx does the same.
    proxy: {
      "/api": { target: "http://localhost:8000", rewrite: (path) => path.replace(/^\/api/, "") },
    },
  },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
});
