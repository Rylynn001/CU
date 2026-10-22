import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        // target: 'http://127.0.0.1:8188',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // multipart/form-data 直接透传给后端。
        bypass: (req) => {
          if (req.headers['content-type']?.includes('multipart/form-data')) {
            return null
          }
        },
      },
      // '/ws': {
      //   // target: 'ws://127.0.0.1:8000',
      //   target: 'ws://127.0.0.1:8188',
      //   ws: true,
      //   changeOrigin: true,
      // },
    },
  },
})
