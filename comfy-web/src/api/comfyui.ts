import { getBaseUrl } from '../config'

// 提交给 ComfyUI /prompt 接口的参数
export interface PromptParams {
  ckpt_name: string        // 模型文件名
  positive_prompt: string  // 正向提示词
  negative_prompt: string  // 反向提示词
  width: number
  height: number
  seed: number
  steps: number            // 采样步数
  cfg: number              // 提示词引导强度
  sampler_name: string
  scheduler: string
  denoise: number          // 去噪强度（图生图时 <1 保留原图结构）
  batch_size: number       // 一次生成几张
  // 图生图：上传后 ComfyUI 返回的文件名
  input_image?: string
}

// 文生图工作流：EmptyLatentImage 生成空白潜空间 → KSampler 采样 → VAEDecode 解码
function buildTxt2ImgWorkflow(p: PromptParams) {
  return {
    '4': { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: p.ckpt_name } },
    '5': { class_type: 'EmptyLatentImage', inputs: { width: p.width, height: p.height, batch_size: p.batch_size } },
    '6': { class_type: 'CLIPTextEncode', inputs: { text: p.positive_prompt, clip: ['4', 1] } },
    '7': { class_type: 'CLIPTextEncode', inputs: { text: p.negative_prompt, clip: ['4', 1] } },
    '3': {
      class_type: 'KSampler',
      inputs: {
        model: ['4', 0], positive: ['6', 0], negative: ['7', 0], latent_image: ['5', 0],
        seed: p.seed, steps: p.steps, cfg: p.cfg,
        sampler_name: p.sampler_name, scheduler: p.scheduler, denoise: p.denoise,
      },
    },
    '8': { class_type: 'VAEDecode', inputs: { samples: ['3', 0], vae: ['4', 2] } },
    '9': { class_type: 'SaveImage', inputs: { filename_prefix: 'ComfyUI', images: ['8', 0] } },
  }
}

// 图生图工作流：LoadImage 加载参考图 → VAEEncode 编码为潜空间，替代 EmptyLatentImage
function buildImg2ImgWorkflow(p: PromptParams) {
  return {
    '4':  { class_type: 'CheckpointLoaderSimple', inputs: { ckpt_name: p.ckpt_name } },
    '10': { class_type: 'LoadImage', inputs: { image: p.input_image, upload: 'image' } },
    '11': { class_type: 'VAEEncode', inputs: { pixels: ['10', 0], vae: ['4', 2] } },
    '6':  { class_type: 'CLIPTextEncode', inputs: { text: p.positive_prompt, clip: ['4', 1] } },
    '7':  { class_type: 'CLIPTextEncode', inputs: { text: p.negative_prompt, clip: ['4', 1] } },
    '3':  {
      class_type: 'KSampler',
      inputs: {
        model: ['4', 0], positive: ['6', 0], negative: ['7', 0], latent_image: ['11', 0],
        seed: p.seed, steps: p.steps, cfg: p.cfg,
        sampler_name: p.sampler_name, scheduler: p.scheduler, denoise: p.denoise,
      },
    },
    '8':  { class_type: 'VAEDecode', inputs: { samples: ['3', 0], vae: ['4', 2] } },
    '9':  { class_type: 'SaveImage', inputs: { filename_prefix: 'ComfyUI', images: ['8', 0] } },
  }
}

// 获取本地 ComfyUI 已安装的 checkpoint 模型列表
export async function getModels(): Promise<string[]> {
  const res = await fetch(`${getBaseUrl()}/models/checkpoints`)
  return res.json()
}

// 获取 KSampler 节点支持的采样器和调度器列表
export async function getKSamplerInfo(): Promise<{ samplers: string[]; schedulers: string[] }> {
  const res = await fetch(`${getBaseUrl()}/object_info/KSampler`)
  const data = await res.json()
  const input = data.KSampler.input.required
  return {
    samplers: input.sampler_name[0] as string[],
    schedulers: input.scheduler[0] as string[],
  }
}

// 上传图片到 ComfyUI input 目录，返回文件名（供 LoadImage 节点使用）
export async function uploadImage(file: File): Promise<string> {
  const formData = new FormData()
  formData.append('image', file)
  formData.append('type', 'input')
  formData.append('overwrite', 'true')
  const res = await fetch(`${getBaseUrl()}/upload/image`, {
    method: 'POST',
    body: formData,
  })
  const data = await res.json()
  // 返回 subfolder/name 格式，LoadImage 节点用这个定位文件
  return data.subfolder ? `${data.subfolder}/${data.name}` : data.name
}

// 提交工作流到 ComfyUI 执行队列
// 根据是否有 input_image 自动选择文生图或图生图工作流
export async function submitPrompt(params: PromptParams, clientId: string): Promise<{ prompt_id: string }> {
  const workflow = params.input_image
    ? buildImg2ImgWorkflow(params)
    : buildTxt2ImgWorkflow(params)

  // 从 localStorage 获取 user_id
  const userStr = localStorage.getItem('user')
  const user = userStr ? JSON.parse(userStr) : null
  const userId = user?.id

  const res = await fetch(`${getBaseUrl()}/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt: workflow,
      client_id: clientId,
      extra_data: {
        user_id: userId,  // 传递 user_id 到后端
      }
    }),
  })
  return res.json()
}

// 拼接 ComfyUI 图片预览 URL（/api/view?filename=...）
export function getImageUrl(filename: string, subfolder = '', type = 'output'): string {
  const params = new URLSearchParams({ filename, subfolder, type })
  return `${getBaseUrl()}/view?${params}`
}
