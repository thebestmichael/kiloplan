import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // forward API calls to the FastAPI dev server (KILOPLAN_API_URL points at another one)
    proxy: {
      '/api': process.env.KILOPLAN_API_URL ?? 'http://localhost:8000',
    },
  },
})
