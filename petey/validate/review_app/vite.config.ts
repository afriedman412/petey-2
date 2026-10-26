// The review page in React, served by blueprint_review.py at /next/ beside the old page at / until it does
// everything the old one does. `npm run dev` serves it with hot reload on 5173, the API passed to the server on 5005.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/next/',
  plugins: [react()],
  build: { outDir: 'dist', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:5005', '/extract': 'http://127.0.0.1:5005' } },
  test: { environment: 'node' },
});
