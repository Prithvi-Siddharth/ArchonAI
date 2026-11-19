import { readFileSync } from 'node:fs'
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

// The About page shows this: package.json is the one place the version number is kept.
const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8')) as { version: string }

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: { __APP_VERSION__: JSON.stringify(version) },
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
