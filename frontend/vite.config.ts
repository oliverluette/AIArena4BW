import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const backend = 'http://127.0.0.1:8321'

// Die gebaute Oberfläche liegt im Python-Paket, damit `uv run aiarena4bw` ohne Node auskommt.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/aiarena4bw/web',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: backend,
        changeOrigin: true,
        // Das Backend nimmt nur Anfragen der eigenen Herkunft an.
        headers: { origin: backend },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
