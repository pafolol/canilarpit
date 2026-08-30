import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // The frontend calls relative paths, so dev traffic is proxied to the API and
  // production only needs VITE_API_BASE_URL when the two are on different origins.
  const target = env.VITE_API_PROXY || 'http://127.0.0.1:8000'
  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_PORT || 5173),
      proxy: {
        '/api': { target, changeOrigin: true },
        '/health': { target, changeOrigin: true },
      },
    },
  }
})
