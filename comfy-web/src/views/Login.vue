<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElInput, ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'

const DEBUG_PIN = '3008'
const router = useRouter()

const mode = ref<'account' | 'pin'>('account')
const username = ref('')
const password = ref('')
const pin = ref('')
const loading = ref(false)

async function enterHome() {
  sessionStorage.setItem('login-reveal-home', '1')
  await router.push('/')
}

async function handleLogin() {
  if (!username.value.trim()) {
    ElMessage.error('请输入用户名')
    return
  }
  if (!password.value.trim()) {
    ElMessage.error('请输入密码')
    return
  }

  loading.value = true
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value.trim(),
        password: password.value.trim(),
      }),
    })

    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || '登录失败')
    }

    const data = await res.json()
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify(data.user))
    ElMessage.success('登录成功')
    await enterHome()
  } catch (error: any) {
    ElMessage.error(error.message || '登录失败')
  } finally {
    loading.value = false
  }
}

async function handlePinLogin() {
  if (pin.value !== DEBUG_PIN) {
    ElMessage.error('PIN 不正确')
    pin.value = ''
    return
  }

  loading.value = true
  localStorage.setItem('token', 'debug-pin-session')
  localStorage.setItem('user', JSON.stringify({ username: 'Debug User', debug: true }))
  ElMessage.success('Debug 登录成功')
  await enterHome()
}

function submit() {
  if (!loading.value) {
    mode.value === 'pin' ? handlePinLogin() : handleLogin()
  }
}

function filterPin(value: string) {
  pin.value = value.replace(/\D/g, '').slice(0, 4)
}
</script>

<template>
  <main class="login-page">
    <div class="ambient ambient-left" />
    <div class="ambient ambient-right" />

    <section class="login-card" aria-labelledby="login-title">
      <header class="card-header">
        <span class="brand-mark" aria-hidden="true" />
        <p class="eyebrow">AI CREATIVE STUDIO</p>
        <h1 id="login-title">灵感，从这里开始</h1>
        <p class="intro">登录你的创作空间</p>
      </header>

      <div class="mode-switch" role="tablist" aria-label="登录方式">
        <button type="button" :class="{ active: mode === 'account' }" @click="mode = 'account'">账号登录</button>
        <button type="button" :class="{ active: mode === 'pin' }" @click="mode = 'pin'">快速 PIN</button>
      </div>

      <form class="form" @submit.prevent="submit">
        <div v-if="mode === 'account'" class="auth-fields">
          <label class="field">
            <span>用户名</span>
            <ElInput v-model="username" placeholder="请输入用户名" size="large" :prefix-icon="User" autocomplete="username" />
          </label>
          <label class="field">
            <span>密码</span>
            <ElInput v-model="password" type="password" placeholder="请输入密码" size="large" :prefix-icon="Lock" show-password autocomplete="current-password" />
          </label>
        </div>

        <div v-else class="pin-panel">
          <p>输入 4 位调试 PIN</p>
          <ElInput
            :model-value="pin"
            class="pin-input"
            inputmode="numeric"
            maxlength="4"
            placeholder="••••"
            autocomplete="one-time-code"
            aria-label="4 位调试 PIN"
            @update:model-value="filterPin"
          />
          <small>仅用于本地 Debug 快速进入</small>
        </div>

        <button class="login-btn" type="submit" :disabled="loading">
          {{ loading ? '正在进入…' : mode === 'pin' ? '快速进入' : '登录' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  overflow: hidden;
  padding: 24px;
  background: #000;
  opacity: 1;
}

.ambient {
  position: absolute;
  width: 420px;
  height: 420px;
  border-radius: 50%;
  filter: blur(160px);
  opacity: 0.45;
  pointer-events: none;
}

.ambient-left { left: -230px; top: 8%; background: rgba(166, 231, 226, 0.11); }
.ambient-right { right: -230px; bottom: 2%; background: rgba(124, 92, 255, 0.1); }

.login-card {
  position: relative;
  width: min(100%, 420px);
  padding: 44px 38px 38px;
  border: 0;
  background: transparent;
  animation: card-enter 0.65s ease both;
}

.card-header { text-align: center; margin-bottom: 28px; }
.brand-mark {
  display: inline-block;
  width: 18px;
  height: 18px;
  margin-bottom: 18px;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 0 28px rgba(166, 231, 226, 0.5);
}
.eyebrow { margin: 0 0 10px; color: rgba(166, 231, 226, 0.7); font-size: 10px; letter-spacing: 0.24em; }
h1 { margin: 0; color: #fff; font-size: 27px; font-weight: 600; letter-spacing: 0.04em; }
.intro { margin: 10px 0 0; color: rgba(255, 255, 255, 0.4); font-size: 13px; }

.mode-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-bottom: 24px;
  padding: 4px;
  border-radius: 12px;
  background: #111;
}
.mode-switch button {
  height: 38px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: rgba(255, 255, 255, 0.42);
  cursor: pointer;
  font-size: 12px;
  transition: background 0.2s ease, color 0.2s ease;
}
.mode-switch button.active { background: #202020; color: #fff; }

.form { display: flex; flex-direction: column; gap: 18px; }
.auth-fields,
.pin-panel {
  height: 150px;
}
.auth-fields { display: flex; flex-direction: column; gap: 18px; }
.field { display: flex; flex-direction: column; gap: 8px; }
.field > span { color: rgba(255, 255, 255, 0.5); font-size: 12px; }
.login-btn {
  width: 100%;
  height: 48px;
  margin-top: 8px;
  border: 1px solid #303030;
  border-radius: 12px;
  background: #f2f2f2;
  color: #090909;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
}
.login-btn:hover:not(:disabled) { background: #fff; transform: translateY(-1px); }
.login-btn:active:not(:disabled) { transform: translateY(0); }
.login-btn:disabled { cursor: wait; opacity: 0.58; }

.pin-panel { display: flex; flex-direction: column; align-items: center; justify-content: center; }
.pin-panel p { margin-bottom: 14px; color: rgba(255, 255, 255, 0.62); font-size: 13px; }
.pin-panel small { margin-top: 12px; color: rgba(255, 255, 255, 0.25); font-size: 11px; }
:deep(.pin-input) { width: 190px; }
:deep(.pin-input .el-input__inner) { height: 52px; text-align: center; font-size: 24px; letter-spacing: 0.42em; padding-left: 0.42em; }

:deep(.el-input__wrapper) { background: #101010 !important; border-color: #242424 !important; }

@keyframes card-enter {
  from { opacity: 0; transform: translateY(16px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@media (max-width: 520px) {
  .login-card { padding: 36px 24px 30px; }
  h1 { font-size: 24px; }
}
</style>
