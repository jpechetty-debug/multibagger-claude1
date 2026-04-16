import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react()
  ],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:9005',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://localhost:9005',
        ws: true,
      }
    }
  }
})
