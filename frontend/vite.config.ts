import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser calls the API on its own origin (/api/...), and the dev and preview
// servers forward those calls to FastAPI, so the backend needs no CORS. Defaults to
// the docker-compose API (bound to 127.0.0.1:8000); override with ARCHONAI_API_URL.
const apiProxy = {
  '/api': { target: process.env.ARCHONAI_API_URL ?? 'http://127.0.0.1:8000' },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
})
