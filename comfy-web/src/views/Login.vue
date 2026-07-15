<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElInput, ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import LiquidButton from '../components/LiquidButton.vue'

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
        <h2 class="title">若晴节点式创作平台</h2>
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

        <LiquidButton
          class="login-btn"
          :loading="loading"
          @click="handleLogin"
        >
          {{ loading ? '登录中...' : '登录' }}
        </LiquidButton>
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

:deep(.el-input),
:deep(.el-input__wrapper),
:deep(.el-input__inner) {
  background: transparent !important;
}

:deep(.el-input__wrapper:hover),
:deep(.el-input__wrapper.is-focus) {
  background: transparent !important;
}

:deep(.el-input__inner:-webkit-autofill),
:deep(.el-input__inner:-webkit-autofill:hover),
:deep(.el-input__inner:-webkit-autofill:focus) {
  -webkit-text-fill-color: rgba(255, 255, 255, 0.92) !important;
  caret-color: rgba(255, 255, 255, 0.92);
  box-shadow: 0 0 0 1000px transparent inset !important;
  transition: background-color 9999s ease-out;
}

.login-btn {
  width: 100%;
  margin-top: 12px;
  letter-spacing: 2px;
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
</style>
