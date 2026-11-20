import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.UNPACK_API || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
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
