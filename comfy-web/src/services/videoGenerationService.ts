import { apiVideoGenerate, apiImg2VideoGenerate, uploadInputImage } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'

export interface VideoGenerateParams {
  modelId: string
  prompt: string
  ratio: string       // 画面比例，如 "16:9"
  resolution: string  // 分辨率，如 "1080p"
  duration: number    // 时长（秒）
  userId?: number
}

// 图生视频额外需要输入素材
export interface VideoImg2VideoParams extends VideoGenerateParams {
  inputFiles: File[]       // 本地上传的文件
  inputAssetIds: number[]  // 从资产库选择的素材 id
}

export interface VideoGenerateResult {
  taskId?: string          // 异步任务 id，有值时需轮询
  videoUrl?: string        // 同步返回时的视频 URL
  inputAssetIds?: number[] // 提交时使用的输入素材 id，用于保存历史
}

/**
 * 提交文生视频任务。
 * 返回 taskId（异步）或 videoUrl（同步）。
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
 * 提交图生视频任务。
 * 先将本地文件上传到资产库，再合并资产库 id 一起提交。
 * 始终返回 taskId（后端图生视频只支持异步）。
 */
export async function submitImg2VideoGeneration(params: VideoImg2VideoParams): Promise<VideoGenerateResult> {
  const userId = params.userId ?? getCurrentUserId() ?? undefined

  // 上传本地文件，获取资产 id
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
