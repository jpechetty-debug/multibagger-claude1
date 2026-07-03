import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react()
  ],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined
          }

          if (
            id.includes('react') ||
            id.includes('react-dom') ||
            id.includes('react-router') ||
            id.includes('@remix-run')
          ) {
            return 'vendor-react'
          }

          if (id.includes('recharts') || id.includes('d3-')) {
            return 'vendor-charts'
          }

          if (id.includes('framer-motion')) {
            return 'vendor-motion'
          }

          if (id.includes('lucide-react')) {
            return 'vendor-icons'
          }

          return undefined
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/setupTests.ts',
  },
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:9005',
        changeOrigin: true,
      },
      '/swarm': {
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
