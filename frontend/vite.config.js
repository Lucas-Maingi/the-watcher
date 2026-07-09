import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // dashboard talks to the fastapi backend; in docker the env var
      // points at the service name instead of localhost
      '/api': process.env.WATCHER_API || 'http://localhost:8000',
    },
  },
})
