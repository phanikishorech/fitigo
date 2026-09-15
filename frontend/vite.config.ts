import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// This repo is sometimes opened via a Windows junction/symlink (e.g. the Cline workspace).
// Vite/Rollup/esbuild can get confused if it mixes symlink paths with real paths during
// dependency optimization (leading to crashes like `Cannot read properties of undefined (reading 'imports')`).
//
// Force Vite to use the *real* path for root + cacheDir to keep all generated paths consistent.
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const realRoot = fs.realpathSync(__dirname)

export default defineConfig(() => ({
  // Use the real path to avoid symlink/junction path mixing.
  root: realRoot,
  plugins: [react()],
  // Default is `false`, but keep it explicit since this project is sometimes run from a symlink.
  resolve: {
    preserveSymlinks: false
  },
  cacheDir: path.join(realRoot, 'node_modules', '.vite-fitigo'),
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
}))
