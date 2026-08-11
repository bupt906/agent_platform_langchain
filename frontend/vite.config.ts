import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      "/chat": "http://localhost:8000",
      "/chat/stream": "http://localhost:8000",
      "/skills": "http://localhost:8000",
      "/audit": "http://localhost:8000",
      "^/review$": "http://localhost:8000",
      "/api/callback": "http://localhost:8000",
      "/preferences": "http://localhost:8000",
      "/artifacts": "http://localhost:8000",
    },
  },
});
