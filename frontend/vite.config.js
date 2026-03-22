import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8000,
    host: true
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/__tests__/setup.js',
    include: ['src/**/*.{test,spec}.{js,jsx}'],
    env: {
      VITE_RESEARCH_API_URL: 'https://test-api.example.com/dev',
      VITE_ANALYSIS_FOLLOWUP_URL: 'https://test-followup.example.com',
      VITE_REST_API_URL: 'https://test-api.example.com/dev',
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/__tests__/**']
    }
  }
})
