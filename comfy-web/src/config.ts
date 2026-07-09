// 本地存储中保存后端地址的 key。
const STORAGE_KEY = 'comfy-web-host'

// 是否为开发模式，由 Vite 注入。
const isDev = import.meta.env.DEV

// 获取 ComfyUI 后端地址，默认 127.0.0.1:8188。
export function getHost(): string {
  return localStorage.getItem(STORAGE_KEY) || '127.0.0.1:8188'
}

// 保存后端地址到本地存储。
export function setHost(host: string) {
  localStorage.setItem(STORAGE_KEY, host)
}

// 获取 HTTP API 基础路径，生产环境通过 Nginx 反向代理 /api。
export function getBaseUrl(): string {
  return '/api'
}

// 获取 WebSocket 地址。开发模式直连 ComfyUI，生产模式跟随当前页面协议和域名。
export function getWsUrl(): string {
  if (isDev) return `ws://${getHost()}/ws`
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/ws`
}
