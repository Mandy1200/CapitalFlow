import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      // In development the UI calls /api on its own origin and Vite forwards it,
      // so no CORS setup is needed. VITE_PROXY_TARGET points at Django.
      proxy: {
        "/api": { target: env.VITE_PROXY_TARGET || "http://localhost:8000", changeOrigin: true },
      },
    },
  };
});
