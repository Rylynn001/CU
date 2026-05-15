const STORAGE_KEY = 'comfy-web-host'
const isDev = import.meta.env.DEV

export function getHost(): string {
  return localStorage.getItem(STORAGE_KEY) || '127.0.0.1:8188'
}

export function setHost(host: string) {
  localStorage.setItem(STORAGE_KEY, host)
}

export function getBaseUrl(): string {
  return '/api'
}

export function getWsUrl(): string {
  if (isDev) return `ws://${getHost()}/ws`
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/ws`
}
