import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// The API port comes from the repository's root .env (the same file the backend reads), with
// API_PORT in the shell taking precedence and 8000 as the fallback. Only the config reads that file:
// the client bundle sees nothing from it (envDir stays in frontend/ and only VITE_* is exposed).
export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, fileURLToPath(new URL("..", import.meta.url)), "API_PORT");
  const apiPort = process.env.API_PORT || rootEnv.API_PORT || "8000";

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      proxy: {
        "/api": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: false },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
      unstubGlobals: true,
    },
  };
});
