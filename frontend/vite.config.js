import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server: forward API + WebSocket calls to the FastAPI backend on :8000,
// so the browser only ever talks to one origin (no CORS needed).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
  },
})
