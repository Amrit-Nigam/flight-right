import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Leaflet was removed (MapLibre/mapcn). Stale node_modules/.vite could still list it.
  optimizeDeps: {
    exclude: ['leaflet', 'react-leaflet'],
  },
})