import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.UNPACK_API || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  // The GitHub Pages build (VITE_STATIC=1) is served from /<repo>/, so assets use relative URLs; the app routes by hash.
  base: process.env.VITE_STATIC === "1" ? "./" : "/",
  server: {
    port: 5173,
    // The graph lab imports contract/fixtures/ (one source of truth for the API shape), which sits outside web/.
    fs: { allow: [".."] },
    proxy: {
      "/api": api,
      "/auth": api,
      "/img": api,
    },
  },
});
