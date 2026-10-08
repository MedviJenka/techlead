import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// Same-origin /api in every environment: Vite proxies it to the backend (localhost or the compose service).
const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig(({ mode }) => {
  // Google sign-in runs through Supabase Auth in the browser. Only the project URL and the *publishable* key are
  // read from the repo's root .env (or the environment); nothing else from it reaches the bundle.
  const env = { ...loadEnv(mode, '..', ''), ...process.env }
  return {
    plugins: [react(), tailwindcss()],
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(env.SUPABASE_PROJECT_URL ?? ''),
      'import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY': JSON.stringify(env.SUPABASE_PUBLISHABLE_KEY ?? ''),
    },
    server: {
      host: true,
      port: 5173,
      proxy: { '/api': { target: apiTarget, changeOrigin: true } },
    },
  }
})
