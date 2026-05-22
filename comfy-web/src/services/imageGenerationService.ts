import { apiGenerate, uploadInputImage, resolveImageSrc } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'

export interface InputImage {
  file: File | null
  preview: string
  assetLocation: string
}

export interface ImageGenerateParams {
  modelId: string
  prompt: string
  width: number
  height: number
  batchSize: number
  img2img: boolean
  inputImages: InputImage[]
  userId?: number
}

export interface ImageGenerateResult {
  taskId?: string
  images?: string[]
}

/**
 * 上传输入图片，返回 asset id 列表
 */
async function uploadInputImages(images: InputImage[], userId: number): Promise<number[]> {
  const ids: number[] = []
  for (const img of images) {
    if (img.file) {
      const uploaded = await uploadInputImage(img.file, userId)
      ids.push(uploaded.id)
    } else if (img.assetLocation) {
      const filename = img.assetLocation.replace(/\\/g, '/').split('/').pop()!
      const res = await fetch(`/api/view?filename=${encodeURIComponent(filename)}&type=output`)
      const blob = await res.blob()
      const file = new File([blob], img.assetLocation, { type: blob.type })
      const uploaded = await uploadInputImage(file, userId)
      ids.push(uploaded.id)
    } else if (img.preview) {
      const res = await fetch(img.preview)
      const blob = await res.blob()
      const file = new File([blob], 'input.png', { type: blob.type || 'image/png' })
      const uploaded = await uploadInputImage(file, userId)
      ids.push(uploaded.id)
    }
  }
  return ids
}

/**
 * 提交图片生成任务。
 * 返回 taskId（异步任务）或 images（同步结果）。
 */
export async function submitImageGeneration(params: ImageGenerateParams): Promise<ImageGenerateResult> {
  const userId = params.userId ?? getCurrentUserId() ?? undefined

  let inputAssetIds: number[] | undefined
  if (params.img2img) {
    if (params.inputImages.length === 0) throw new Error('请先上传或选择参考图片')
    inputAssetIds = await uploadInputImages(params.inputImages, userId ?? 1)
  }

  const result = await apiGenerate({
    model: params.modelId,
    prompt: params.prompt,
    width: params.width,
    height: params.height,
    n: params.batchSize,
    input_asset_ids: inputAssetIds,
    user_id: userId,
  })

  if (result.taskId) {
    return { taskId: result.taskId }
  }

  return {
    images: result.images.map(resolveImageSrc).filter(Boolean),
  }
}
