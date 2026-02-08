import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],

  server: {
    proxy: {
      "/api": "http://localhost:8080",
      "/auth": "http://localhost:8080",
      "/logout": "http://localhost:8080",
    },
  },

  base: "./",

  build: {
    outDir: path.resolve(__dirname, "../extension"),
    emptyOutDir: false, // don't delete manifest.json
    rollupOptions: {
      input: {
        popup: path.resolve(__dirname, "popup.html"),
      },
    },
  },
});
