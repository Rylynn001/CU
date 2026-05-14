<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElInput, ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()

const username = ref('')
const password = ref('')
const loading = ref(false)

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

    // 保存 token 和用户信息
    localStorage.setItem('token', data.token)
    localStorage.setItem('user', JSON.stringify(data.user))

    ElMessage.success('登录成功')
    router.push('/')
  } catch (e: any) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    handleLogin()
  }
}
</script>

<template>
  <div class="login-page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="login-card">
      <div class="card-header">
        <h2 class="title">泰然若晴</h2>
        <p class="subtitle">AI Creative Studio</p>
      </div>

      <div class="form">
        <div class="field">
          <label class="label">用户名</label>
          <ElInput
            v-model="username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
            @keydown="handleKeydown"
          />
        </div>

        <div class="field">
          <label class="label">密码</label>
          <ElInput
            v-model="password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keydown="handleKeydown"
          />
        </div>

        <button
          class="login-btn"
          :class="{ loading }"
          :disabled="loading"
          @click="handleLogin"
        >
          <span class="btn-glow" />
          <span class="btn-label">{{ loading ? '登录中...' : '登录' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  animation: breathe 6s ease-in-out infinite;
}
.orb-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(108,99,255,0.16) 0%, transparent 70%);
  top: -140px; left: 40px;
}
.orb-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(167,139,250,0.12) 0%, transparent 70%);
  bottom: -100px; right: 60px;
  animation-delay: 3s;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 400px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 24px;
  padding: 40px 36px;
  backdrop-filter: blur(16px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}

.card-header {
  text-align: center;
  margin-bottom: 32px;
}

.title {
  font-size: 28px;
  font-weight: 700;
  color: rgba(255,255,255,0.92);
  letter-spacing: 3px;
  margin: 0 0 8px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.subtitle {
  font-size: 12px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 2px;
  text-transform: uppercase;
  margin: 0;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.label {
  font-size: 12px;
  color: rgba(255,255,255,0.5);
  letter-spacing: 0.5px;
}

.login-btn {
  position: relative;
  width: 100%;
  height: 46px;
  margin-top: 12px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  overflow: hidden;
  background: linear-gradient(135deg, #6c63ff, #a78bfa, #6c63ff);
  background-size: 200% auto;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 2px;
  transition: opacity 0.2s, transform 0.15s;
  animation: shimmer 3s linear infinite;
}
.login-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  opacity: 0.9;
}
.login-btn:active:not(:disabled) {
  transform: translateY(0);
}
.login-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  animation: none;
}
.login-btn.loading {
  animation: breathe 2s ease-in-out infinite;
}

.btn-glow {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: inherit;
  filter: blur(12px);
  opacity: 0;
  transition: opacity 0.3s;
  z-index: -1;
}
.login-btn:not(:disabled):hover .btn-glow {
  opacity: 0.5;
}
.btn-label {
  position: relative;
  z-index: 1;
}

@keyframes shimmer {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
</style>
