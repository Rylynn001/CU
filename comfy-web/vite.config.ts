import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    hmr: {
      port: 5175,
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8188',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // 不要修改任何 header，直接透传
        bypass: (req, res, options) => {
          // 对于 multipart/form-data，直接透传，不做任何处理
          if (req.headers['content-type']?.includes('multipart/form-data')) {
            // 返回 null 让 proxy 正常处理，但不修改 headers
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
