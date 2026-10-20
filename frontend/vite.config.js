import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The API token lives in frontend/.env.local as NIGHTMARE_TOKEN (no VITE_ prefix, so it is
// never bundled into the browser). The dev server's proxy adds it to every /api request.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const token = env.NIGHTMARE_TOKEN || ''
  const backend = env.NIGHTMARE_BACKEND || 'http://127.0.0.1:8000'

  if (!token) {
    console.warn(
      '\n[nightmare] NIGHTMARE_TOKEN is missing. Copy .env.local.example to .env.local and use the same token as backend/.env\n',
    )
  }

  const proxy = {
    '/api': {
      target: backend,
      changeOrigin: false, // keep Host as 127.0.0.1:5173 so the backend's local-host check passes
      rewrite: (path) => path.replace(/^\/api/, ''),
      headers: { 'X-Nightmare-Token': token },
      timeout: 180_000, // agy can take 10-20 s per call
      proxyTimeout: 180_000,
    },
  }

  return {
    plugins: [react(), tailwindcss()],
    server: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
    preview: { host: '127.0.0.1', port: 5173, strictPort: true, proxy },
  }
})
