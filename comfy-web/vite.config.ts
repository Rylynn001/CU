import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

const fullReloadOnChange = {
  name: 'full-reload-on-change',
  apply: 'serve' as const,
  handleHotUpdate({ server }: { server: { ws: { send: (payload: { type: 'full-reload' }) => void } } }) {
    server.ws.send({ type: 'full-reload' })
    return []
  },
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendUrl = env.VITE_BACKEND_URL || 'http://127.0.0.1:8188'

  return {
  plugins: [vue(), fullReloadOnChange],
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        // multipart/form-data 直接透传给 ComfyUI。
        bypass: (req) => {
          if (req.headers['content-type']?.includes('multipart/form-data')) {
            return null
          }
        },
      },
      '/ws': {
        target: backendUrl.replace(/^http/, 'ws'),
        ws: true,
        changeOrigin: true,
      },
    },
  },
  }
})
