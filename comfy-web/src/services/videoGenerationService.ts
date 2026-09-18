import { apiVideoGenerate, apiImg2VideoGenerate, uploadInputImage } from '../api/apiService'

export interface VideoGenerateParams {
  modelId: string | number
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
  file?: File
}

export interface VideoImg2VideoParams extends VideoGenerateParams {
  inputFiles?: File[]
  inputAssetPreviews?: AssetPreview[]
  inputAssetIds?: number[]
  audioFile?: File // 可选背景音频
}

export interface VideoGenerateResult {
  taskId?: string
  historyId?: number
  videoUrl?: string
  inputAssetIds?: number[]
}

export async function submitVideoGeneration(params: VideoGenerateParams): Promise<VideoGenerateResult> {
  const result = await apiVideoGenerate({
    model: params.modelId,
    prompt: params.prompt,
    ratio: params.ratio,
    resolution: params.resolution,
    duration: params.duration,
  })

  if ('task_id' in result) {
    return { taskId: result.task_id, historyId: result.history_id }
  }
  return { videoUrl: result.video_url }
}

export async function submitImg2VideoGeneration(params: VideoImg2VideoParams): Promise<VideoGenerateResult> {
  const allIds: number[] = [...(params.inputAssetIds ?? [])]

  // 上传本地文件
  for (const file of params.inputFiles ?? []) {
    const res = await uploadInputImage(file)
    allIds.push(res.id)
  }

  for (const asset of params.inputAssetPreviews ?? []) {
    if (asset.file) {
      const res = await uploadInputImage(asset.file)
      allIds.push(res.id)
    } else {
      allIds.push(asset.id)
    }
  }

  if (params.audioFile) {
    const res = await uploadInputImage(params.audioFile)
    allIds.push(res.id)
  }

  const result = await apiImg2VideoGenerate({
    model: params.modelId,
    prompt: params.prompt,
    ratio: params.ratio,
    resolution: params.resolution,
    duration: params.duration,
    input_asset_ids: allIds,
  })

  return { taskId: result.task_id, historyId: result.history_id, inputAssetIds: allIds }
}
