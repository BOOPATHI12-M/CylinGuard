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
    rollupOptions: {
      output: {
        // Recharts plus its d3 dependencies are about half the bundle and are only
        // needed on the pages that draw charts. Splitting them keeps the first paint -
        // which includes the login form and the emergency banner - small.
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          charts: ['recharts'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
