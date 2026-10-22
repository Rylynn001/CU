// AI 模型类型定义

export interface ReasoningLevel {
  id: string
  label: string
  desc: string
  multiplier: number
}

export interface AIModel {
  id: string
  name: string
  provider: string
  tag?: string
  iconName: 'openai' | 'anthropic' | 'gemini' | 'mistral'
  badgeColor: string
  accentColor: string
  reasoningTitle: string
  defaultLevel: string
  levels: ReasoningLevel[]
}

export interface AttachedFile {
  name: string
  isImage: boolean
  file?: File
}

export interface ChatSubmitData {
  prompt: string
  model: AIModel
  effort: string
  useWebSearch: boolean
  attachedFile: AttachedFile | null
}

export const DEFAULT_AI_MODELS: AIModel[] = [
  {
    id: 'gpt-5',
    name: 'GPT-5',
    provider: 'OpenAI',
    tag: 'Thinking',
    iconName: 'openai',
    badgeColor: 'text-emerald-500',
    accentColor: '#10a37f',
    reasoningTitle: '推理强度',
    defaultLevel: 'high',
    levels: [
      { id: 'low', label: '低', desc: '快速响应，简洁分析', multiplier: 1.8 },
      { id: 'medium', label: '中', desc: '平衡的逐步推理', multiplier: 2.6 },
      { id: 'high', label: '高', desc: '深入推理复杂任务', multiplier: 3.6 },
      { id: 'max', label: '最大', desc: '最大计算深度和综合', multiplier: 4.8 },
    ],
  },
  {
    id: 'claude-fable-5-1',
    name: 'Claude Fable 5.1',
    provider: 'Anthropic',
    tag: 'Mythos',
    iconName: 'anthropic',
    badgeColor: 'text-amber-500',
    accentColor: '#d97706',
    reasoningTitle: '思考预算',
    defaultLevel: 'high',
    levels: [
      { id: 'medium', label: '中', desc: '标准工作流的结构化思考', multiplier: 2.4 },
      { id: 'high', label: '高', desc: '复杂工作流的深度分析推理', multiplier: 3.6 },
      { id: 'max', label: '最大', desc: '最大深思熟虑的自主综合', multiplier: 4.8 },
    ],
  },
  {
    id: 'gemini-3-8',
    name: 'Gemini 3.8 Flash',
    provider: 'Google',
    tag: 'Agentic',
    iconName: 'gemini',
    badgeColor: 'text-blue-500',
    accentColor: '#3b82f6',
    reasoningTitle: '扩展思考',
    defaultLevel: 'medium',
    levels: [
      { id: 'low', label: '低', desc: '最小延迟和直接响应', multiplier: 1.6 },
      { id: 'medium', label: '中', desc: '平衡的多模态推理', multiplier: 2.6 },
      { id: 'high', label: '高', desc: '扩展思考与交叉验证', multiplier: 3.8 },
    ],
  },
  {
    id: 'mistral-large-4',
    name: 'Mistral Large 4',
    provider: 'Mistral AI',
    tag: '1T Multimodal',
    iconName: 'mistral',
    badgeColor: 'text-orange-500',
    accentColor: '#f97316',
    reasoningTitle: '推理模式',
    defaultLevel: 'medium',
    levels: [
      { id: 'low', label: '低', desc: '敏捷推理，无思维链', multiplier: 1.8 },
      { id: 'medium', label: '中', desc: '标准多模态逻辑和推理', multiplier: 2.8 },
      { id: 'max', label: '最大', desc: '全面审计和形式验证', multiplier: 4.6 },
    ],
  },
  {
    id: 'o3-mini',
    name: 'o3-mini',
    provider: 'OpenAI',
    tag: 'Reasoning',
    iconName: 'openai',
    badgeColor: 'text-emerald-400',
    accentColor: '#10a37f',
    reasoningTitle: '推理强度',
    defaultLevel: 'high',
    levels: [
      { id: 'low', label: '低', desc: '高速度，基本逻辑', multiplier: 1.6 },
      { id: 'medium', label: '中', desc: '平衡的数学和分析流程', multiplier: 2.8 },
      { id: 'high', label: '高', desc: '密集的形式算法验证', multiplier: 4.2 },
    ],
  },
]
