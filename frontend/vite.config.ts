import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Bind IPv4 explicitly. Vite's default `localhost` resolves to `::1` on
    // Node 18+, which leaves anything reaching for 127.0.0.1 — including the
    // backend on the other side of this proxy — looking at a closed port.
    host: '127.0.0.1',
    // The backend owns `/api`. Proxying in development keeps the browser
    // same-origin, so the API needs no CORS middleware — and CORS is a
    // setting a desktop build would have to get right for no benefit, because
    // in the shipped app the two run inside one process.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
