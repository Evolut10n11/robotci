import { fileURLToPath, URL } from "node:url";
import { existsSync, readFileSync } from "node:fs";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  plugins: [
    {
      name: "local-viewer-session",
      configureServer(server) {
        const fixture = fileURLToPath(
          new URL("./.preview/session.json", import.meta.url),
        );
        server.middlewares.use("/api/session", (request, response, next) => {
          if (request.method !== "GET" || !existsSync(fixture)) return next();
          response.setHeader("Content-Type", "application/json");
          response.setHeader("Cache-Control", "no-store");
          response.end(readFileSync(fixture));
        });
      },
    },
  ],
  server: {
    allowedHosts: ["terminal.local"],
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  build: {
    outDir: fileURLToPath(new URL("../robotci/viewer_assets", import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
  },
});
