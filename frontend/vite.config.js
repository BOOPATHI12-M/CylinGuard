import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In production NGINX proxies /api and /ws to the backend, so the app always
// talks to same-origin relative paths. In local dev Vite plays that role.
const BACKEND = process.env.BACKEND_ORIGIN ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/ws': { target: BACKEND, ws: true, changeOrigin: true },
      // /health is outside /api. Without this it falls through to the SPA fallback and
      // returns index.html with a 200, so the check could never fail.
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
