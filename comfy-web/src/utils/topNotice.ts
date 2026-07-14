export const TOP_NOTICE_EVENT = 'rqvfx:top-notice'
export type TopNoticeType = 'success' | 'warning' | 'error' | 'info'

export function showTopNotice(message: string, type: TopNoticeType = 'info', duration = 10000) {
  window.dispatchEvent(new CustomEvent(TOP_NOTICE_EVENT, {
    detail: { message, type, duration },
  }))
}
