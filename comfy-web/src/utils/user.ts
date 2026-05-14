export function getCurrentUserId(): number | undefined {
  try {
    const userStr = localStorage.getItem('user')
    return userStr ? JSON.parse(userStr).id : undefined
  } catch {
    return undefined
  }
}
