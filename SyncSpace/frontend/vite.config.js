import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Proxy API requests to the FastAPI backend during development.
    // Any request to /api/* will be forwarded to http://localhost:8000.
    // This avoids CORS issues and mirrors a production reverse-proxy setup.
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
