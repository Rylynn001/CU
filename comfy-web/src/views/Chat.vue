<template>
  <div class="chat-page dark">
    <div class="chat-content">
      <div v-if="isLoadingModels" class="loading-container">
        <p>正在加载模型...</p>
      </div>
      <AiMascotInput
        v-else
        title="我能为您做什么？"
        subtitle="输入提示词或语音输入开始对话"
        :show-welcome="true"
        :on-submit="handleSubmit"
        :is-processing="isProcessing"
        :models="availableModels"
        :default-model-id="availableModels[0]?.id"
        :enable-voice="true"
        :enable-web-search="true"
        :enable-attachments="true"
      />

      <div v-if="messages.length > 0" class="messages-container">
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          :class="['message', msg.role]"
        >
          <div class="message-content">
            <strong>{{ msg.role === 'user' ? '你' : 'AI' }}:</strong>
            <p>{{ msg.content }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AiMascotInput from '@/components/AiMascotInput.vue'
import type { ChatSubmitData, AIModel } from '@/types/ai-models'
import { sendWorkflowMessage, getLanguageModels } from '@/api/workflow'

const isProcessing = ref(false)
const messages = ref<Array<{ role: 'user' | 'assistant'; content: string }>>([])
const availableModels = ref<AIModel[]>([])
const isLoadingModels = ref(true)

// 从后端数据构建前端 AIModel 格式
function buildAIModel(backendModel: any): AIModel {
  // 根据 provider 决定图标和配色
  const providerMap: Record<string, { iconName: AIModel['iconName']; badgeColor: string; accentColor: string }> = {
    openai: {
      iconName: 'openai',
      badgeColor: 'text-emerald-500',
      accentColor: '#10a37f',
    },
    anthropic: {
      iconName: 'anthropic',
      badgeColor: 'text-amber-500',
      accentColor: '#d97706',
    },
    gemini: {
      iconName: 'gemini',
      badgeColor: 'text-blue-500',
      accentColor: '#3b82f6',
    },
    mistral: {
      iconName: 'mistral',
      badgeColor: 'text-orange-500',
      accentColor: '#f97316',
    },
  }

  const providerKey = backendModel.provider.toLowerCase()
  const providerConfig = providerMap[providerKey] || providerMap.openai

  return {
    id: String(backendModel.id),
    name: backendModel.name,
    provider: backendModel.provider,
    iconName: providerConfig.iconName,
    badgeColor: providerConfig.badgeColor,
    accentColor: providerConfig.accentColor,
    reasoningTitle: '推理强度',
    defaultLevel: 'medium',
    levels: [
      { id: 'low', label: '低', desc: '快速响应', multiplier: 1.8 },
      { id: 'medium', label: '中', desc: '平衡推理', multiplier: 2.6 },
      { id: 'high', label: '高', desc: '深度推理', multiplier: 3.6 },
    ],
  }
}

// 加载语言模型列表
async function loadLanguageModels() {
  try {
    isLoadingModels.value = true
    const models = await getLanguageModels()
    availableModels.value = models.map(buildAIModel)
    console.log('已加载语言模型:', availableModels.value)
  } catch (error) {
    console.error('加载语言模型失败:', error)
    // 如果加载失败，使用默认模型
    availableModels.value = [
      {
        id: 'fallback',
        name: 'GPT-4',
        provider: 'OpenAI',
        iconName: 'openai',
        badgeColor: 'text-emerald-500',
        accentColor: '#10a37f',
        reasoningTitle: '推理强度',
        defaultLevel: 'medium',
        levels: [
          { id: 'low', label: '低', desc: '快速响应', multiplier: 1.8 },
          { id: 'medium', label: '中', desc: '平衡推理', multiplier: 2.6 },
          { id: 'high', label: '高', desc: '深度推理', multiplier: 3.6 },
        ],
      },
    ]
  } finally {
    isLoadingModels.value = false
  }
}

onMounted(() => {
  loadLanguageModels()
})

const handleSubmit = async (data: ChatSubmitData) => {
  console.log('用户提交:', data)

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: data.prompt,
  })

  isProcessing.value = true

  try {
    // 调用后端 API
    const response = await sendWorkflowMessage({
      message: data.prompt,
      session_id: 'test-session-' + Date.now(),
    })

    // 添加 AI 回复
    messages.value.push({
      role: 'assistant',
      content: response.reply || '收到！我正在处理您的请求...',
    })
  } catch (error) {
    console.error('发送消息失败:', error)
    messages.value.push({
      role: 'assistant',
      content: '抱歉，处理您的请求时出现错误。',
    })
  } finally {
    isProcessing.value = false
  }
}
</script>

<style scoped>
.chat-page {
  position: relative;
  z-index: 1;
  width: 100%;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem 1rem;
  font-family: 'Space Grotesk', 'Inter', system-ui, -apple-system, sans-serif;
  background: #000;
  color: #fff;
}

.chat-content {
  width: 100%;
  max-width: 48rem;
}

.loading-container {
  text-align: center;
  padding: 2rem;
  color: rgba(255, 255, 255, 0.6);
}

.messages-container {
  width: 100%;
  max-width: 48rem;
  margin-top: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.message {
  padding: 1rem 1.5rem;
  border-radius: 1rem;
  background: #18181b;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.message.user {
  margin-left: auto;
  max-width: 80%;
  background: rgba(16, 163, 127, 0.16);
  border: 1px solid rgba(16, 163, 127, 0.2);
}

.message.assistant {
  margin-right: auto;
  max-width: 80%;
}

.message-content strong {
  display: block;
  margin-bottom: 0.5rem;
  color: #f4f4f5;
  font-weight: 600;
}

.message-content p {
  margin: 0;
  color: #d4d4d8;
  line-height: 1.6;
}
</style>
