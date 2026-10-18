import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 生产部署在 Caddy 的 /pumpfun/ 路径下（handle_path 会剥掉前缀），
// 所以 build 时 base 必须是 /pumpfun/；dev 时用 / 并靠 proxy 转发到 BFF。
export default defineConfig(({ mode }) => ({
  base: mode === "production" ? "/pumpfun/" : "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", sourcemap: false },
}));
