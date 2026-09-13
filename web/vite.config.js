import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  server: {
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
