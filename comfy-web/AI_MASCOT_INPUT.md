# AI Mascot Input 组件 - Vue 3 版本

## 概述

这是一个从 React 转换为 Vue 3 的 AI 聊天输入组件，具有以下特性：

- 🤖 可爱的机器人吉祥物动画
- 🎤 语音输入支持（Web Speech API）
- 📎 文件附件上传
- 🌐 网络搜索开关
- 🎨 多 AI 模型选择
- ⚡ 可调节推理强度
- 🌗 深色/浅色模式支持

## 技术栈

- Vue 3 + TypeScript + Composition API
- Tailwind CSS（样式）
- @vueuse/motion（动画）

## 文件结构

```
src/
├── components/
│   ├── AiMascotInput.vue        # 主输入组件
│   ├── RobotBeta.vue            # 机器人吉祥物
│   ├── EyeLED.vue               # 机器人眼睛
│   └── icons/
│       ├── AIProviderIcons.vue  # AI 提供商图标
│       └── IconComponents.vue   # 通用图标
├── types/
│   └── ai-models.ts             # AI 模型类型定义
└── views/
    ├── Chat.vue                 # 真实聊天页面
    └── ChatDemo.vue             # 演示页面
```

## 使用方法

### 基础用法

```vue
<template>
  <AiMascotInput
    title="我能为您做什么？"
    subtitle="输入提示词或语音输入"
    :show-welcome="true"
    :on-submit="handleSubmit"
    :is-processing="isProcessing"
  />
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AiMascotInput from '@/components/AiMascotInput.vue'
import type { ChatSubmitData } from '@/types/ai-models'

const isProcessing = ref(false)

const handleSubmit = async (data: ChatSubmitData) => {
  console.log('用户输入:', data.prompt)
  console.log('选择的模型:', data.model.name)
  console.log('推理强度:', data.effort)
  console.log('网络搜索:', data.useWebSearch)
  console.log('附件:', data.attachedFile)

  isProcessing.value = true
  // 调用 API...
  isProcessing.value = false
}
</script>
```

### Props

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `onSubmit` | `(data: ChatSubmitData) => void \| Promise<void>` | - | 提交回调 |
| `isProcessing` | `boolean` | `false` | 是否正在处理 |
| `value` | `string` | - | 受控输入值 |
| `onChange` | `(value: string) => void` | - | 输入变化回调 |
| `disabled` | `boolean` | `false` | 是否禁用 |
| `placeholder` | `string` | `'我能为您做什么？...'` | 占位符 |
| `title` | `string` | `'我能为您做什么？'` | 欢迎标题 |
| `subtitle` | `string` | `'输入提示词...'` | 欢迎副标题 |
| `showWelcome` | `boolean` | `true` | 显示欢迎横幅 |
| `models` | `AIModel[]` | `DEFAULT_AI_MODELS` | 可用模型列表 |
| `defaultModelId` | `string` | `'gpt-5'` | 默认模型 ID |
| `enableVoice` | `boolean` | `true` | 启用语音输入 |
| `enableWebSearch` | `boolean` | `true` | 启用网络搜索 |
| `enableAttachments` | `boolean` | `true` | 启用附件上传 |
| `className` | `string` | `''` | 额外 CSS 类 |
| `containerClassName` | `string` | `''` | 容器 CSS 类 |

### ChatSubmitData 类型

```typescript
interface ChatSubmitData {
  prompt: string                // 用户输入
  model: AIModel                // 选择的模型
  effort: string                // 推理强度 (low/medium/high/max)
  useWebSearch: boolean         // 是否使用网络搜索
  attachedFile: AttachedFile | null  // 附件
}
```

## 自定义 AI 模型

```typescript
import type { AIModel } from '@/types/ai-models'

const customModels: AIModel[] = [
  {
    id: 'my-model',
    name: '我的模型',
    provider: '我的公司',
    tag: 'Beta',
    iconName: 'openai',  // 可选: openai | anthropic | gemini | mistral
    badgeColor: 'text-purple-500',
    accentColor: '#a855f7',
    reasoningTitle: '思考级别',
    defaultLevel: 'medium',
    levels: [
      { id: 'low', label: '低', desc: '快速响应', multiplier: 1.5 },
      { id: 'medium', label: '中', desc: '平衡', multiplier: 2.5 },
      { id: 'high', label: '高', desc: '深度思考', multiplier: 3.5 },
    ],
  },
]
```

## 演示

访问 `/chat-demo` 路由查看完整演示。

## 开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 访问演示页面
# http://localhost:5174/#/chat-demo
```

## React 到 Vue 3 转换说明

### 主要变化

1. **状态管理**
   - `useState` → `ref`
   - `useEffect` → `watch` / `onMounted` / `onUnmounted`
   - `useRef` → `ref` (不同类型)

2. **动画**
   - `framer-motion` → Vue 的 `<Transition>` + CSS
   - 自定义动画使用 `requestAnimationFrame`

3. **图标**
   - `react-icons` → 自定义 SVG 组件
   - 使用 Phosphor Icons 的路径数据

4. **样式**
   - Tailwind CSS 保持一致
   - 添加了 `Space Grotesk` 字体

5. **语音识别**
   - Web Speech API 保持一致
   - 添加了中文语言支持

## 注意事项

- 语音识别在 Chrome/Edge 中效果最佳
- Safari 可能需要 HTTPS
- 不支持的浏览器会使用模拟输入
- 深色模式需要在根元素添加 `dark` 类

## License

MIT
