import { apiGenerate, uploadInputImage, resolveImageSrc } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'

export interface InputImage {
  file: File | null          // 本地上传的文件，优先使用
  preview: string            // 预览 URL（file 为 null 时用于重新上传）
  assetLocation: string      // 资产库中的存储路径（从资产库选择时有值）
  assetId?: number | null    // 资产库中的 id，有值时直接使用，不再上传
}

export interface ImageGenerateParams {
  modelId: number
  prompt: string
  aspect_ratio: string       // 比例，如 "1:1"、"16:9"
  quality: string            // 清晰度，如 "low"/"medium"/"high"
  batchSize: number
  img2img: boolean           // true 表示图生图模式
  inputImages: InputImage[]  // 图生图时的参考图列表
  userId?: number
}

export interface ImageGenerateResult {
  taskId?: string    // 异步任务 id，有值时需轮询
  historyId?: number // 后端历史记录 id，用于节点面板持久化
  images?: string[]  // 同步返回时的图片 URL 列表
}

/**
 * 将输入图片上传到后端资产库，返回资产 id 列表。
 * 支持两种来源：本地 File 对象、预览 URL（preview 在各场景下都已是正确可访问的地址，
 * 无需再根据 assetLocation 重新拼接，避免拼出错误的 /api/view?type=output 请求）。
 */
async function uploadInputImages(images: InputImage[], userId: number): Promise<number[]> {
  const ids: number[] = []
  for (const img of images) {
    if (img.assetId != null) {
      // 从资产库直接引用，无需上传
      ids.push(img.assetId)
    } else if (img.file) {
      const uploaded = await uploadInputImage(img.file, userId)
      ids.push(uploaded.id)
    } else if (img.preview) {
      const res = await fetch(img.preview)
      if (!res.ok) throw new Error(`获取参考图失败: ${res.status}`)
      const blob = await res.blob()
      const file = new File([blob], 'input.png', { type: blob.type || 'image/png' })
      const uploaded = await uploadInputImage(file, userId)
      ids.push(uploaded.id)
    }
  }
  return ids
}

/**
 * 提交图片生成任务（文生图 / 图生图）。
 * 图生图时先上传参考图，再调用 apiGenerate。
 * 返回 taskId（异步）或 images（同步）。
 */
export async function submitImageGeneration(params: ImageGenerateParams): Promise<ImageGenerateResult> {
  const userId = params.userId ?? getCurrentUserId() ?? undefined

  let inputAssetIds: number[] | undefined
  if (params.img2img) {
    if (params.inputImages.length === 0) throw new Error('请先上传或选择参考图片')
    inputAssetIds = await uploadInputImages(params.inputImages, userId ?? 1)
  }

  const result = await apiGenerate({
    model: String(params.modelId),
    prompt: params.prompt,
    aspect_ratio: params.aspect_ratio,
    quality: params.quality,
    n: params.batchSize,
    input_asset_ids: inputAssetIds,
    user_id: userId,
  })

  if (result.taskId) {
    return { taskId: result.taskId, historyId: result.historyId }
  }

  return {
    images: result.images.map(resolveImageSrc).filter(Boolean),
  }
}
