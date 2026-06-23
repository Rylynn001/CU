import { apiVideoGenerate, apiImg2VideoGenerate, uploadInputImage } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'

export interface VideoGenerateParams {
  modelId: string
  prompt: string
  ratio: string
  resolution: string
  duration: number
  userId?: number
}

export interface AssetPreview {
  id: number
  url: string
  type: 'image' | 'video'
}

export interface VideoImg2VideoParams extends VideoGenerateParams {
  inputFiles: File[]
  inputAssetPreviews: AssetPreview[]
  audioFile?: File // 可选背景音频
}

export interface VideoGenerateResult {
  taskId?: string
  videoUrl?: string
  inputAssetIds?: number[]
}

export async function submitVideoGeneration(params: VideoGenerateParams): Promise<VideoGenerateResult> {
  const userId = params.userId ?? getCurrentUserId() ?? undefined

  const result = await apiVideoGenerate({
    model: params.modelId,
    prompt: params.prompt,
    user_id: userId,
    ratio: params.ratio,
    resolution: params.resolution,
    duration: params.duration,
  })

  if ('task_id' in result) {
    return { taskId: result.task_id }
  }
  return { videoUrl: result.video_url }
}

export async function submitImg2VideoGeneration(params: VideoImg2VideoParams): Promise<VideoGenerateResult> {
  const userId = params.userId ?? getCurrentUserId() ?? undefined

  const allIds: number[] = []

  // 上传本地文件
  for (const file of params.inputFiles) {
    const res = await uploadInputImage(file, userId ?? 1)
    allIds.push(res.id)
  }

  // 从资产库选的素材：下载后上传到 input_assets 表
  for (const asset of params.inputAssetPreviews) {
    const res = await fetch(asset.url)
    const blob = await res.blob()
    const ext = asset.type === 'video' ? 'mp4' : 'png'
    const file = new File([blob], `asset_${asset.id}.${ext}`, { type: blob.type })
    const uploaded = await uploadInputImage(file, userId ?? 1)
    allIds.push(uploaded.id)
  }

  // 上传音频（可选），和图片/视频走同一套上传流程
  if (params.audioFile) {
    const res = await uploadInputImage(params.audioFile, userId ?? 1)
    allIds.push(res.id)
  }

  const result = await apiImg2VideoGenerate({
    model: params.modelId,
    prompt: params.prompt,
    user_id: userId,
    ratio: params.ratio,
    resolution: params.resolution,
    duration: params.duration,
    input_asset_ids: allIds,
  })

  return { taskId: result.task_id, inputAssetIds: allIds }
}
