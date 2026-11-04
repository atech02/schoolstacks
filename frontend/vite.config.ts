import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/images': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/admin/download': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/student/report-card': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/s/': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
});
