const STORAGE_KEY = 'comfy-web-host'
const isDev = import.meta.env.DEV

export function getHost(): string {
  return localStorage.getItem(STORAGE_KEY) || '127.0.0.1:8188'
}

export function setHost(host: string) {
  localStorage.setItem(STORAGE_KEY, host)
}

export function getBaseUrl(): string {
  // 开发环境走 Vite 代理（/api → ComfyUI），避免 HTTP 跨域
  if (isDev) return '/api'
  return `http://${getHost()}`
}

export function getWsUrl(): string {
  // 直连 ComfyUI（后端已关闭 CSRF 校验）
  return `ws://${getHost()}/ws`
}
