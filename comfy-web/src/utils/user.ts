// 从 localStorage 读取当前登录用户的 id
// 登录时后端返回的 user 对象存在 localStorage['user'] 里
export function getCurrentUserId(): number | undefined {
  try {
    const userStr = localStorage.getItem('user')
    return userStr ? JSON.parse(userStr).id : undefined
  } catch {
    return undefined
  }
}
