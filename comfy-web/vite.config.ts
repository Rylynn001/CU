import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8188',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // multipart/form-data 直接透传给 ComfyUI。
        bypass: (req) => {
          if (req.headers['content-type']?.includes('multipart/form-data')) {
            return null
          }
        },
      },
      '/ws': {
        target: 'ws://127.0.0.1:8188',
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
