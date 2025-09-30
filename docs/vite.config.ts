import { defineConfig } from 'vite'

export default defineConfig(({ mode }) => ({
  root: '.',
  base: mode === 'production' ? '/GameLove/' : '/',
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: './index.html'
      }
    }
  },
  server: {
    port: 3000,
    open: true
  }
}))