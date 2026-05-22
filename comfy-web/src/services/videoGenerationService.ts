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

export interface VideoImg2VideoParams extends VideoGenerateParams {
  inputFiles: File[]
  inputAssetIds: number[]
}

export interface VideoGenerateResult {
  taskId?: string
  videoUrl?: string
  inputAssetIds?: number[]
}

/**
 * 文生视频
 */
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

/**
 * 图生视频：先上传本地文件，再提交任务
 */
export async function submitImg2VideoGeneration(params: VideoImg2VideoParams): Promise<VideoGenerateResult> {
  const userId = params.userId ?? getCurrentUserId() ?? undefined

  const uploadedIds: number[] = []
  for (const file of params.inputFiles) {
    const res = await uploadInputImage(file, userId ?? 1)
    uploadedIds.push(res.id)
  }
  const allAssetIds = [...uploadedIds, ...params.inputAssetIds]

  const result = await apiImg2VideoGenerate({
    model: params.modelId,
    prompt: params.prompt,
    user_id: userId,
    ratio: params.ratio,
    resolution: params.resolution,
    duration: params.duration,
    input_asset_ids: allAssetIds,
  })

  return { taskId: result.task_id, inputAssetIds: allAssetIds }
}
