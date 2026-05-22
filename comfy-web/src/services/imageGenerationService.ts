import { apiGenerate, uploadInputImage, resolveImageSrc } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'

export interface InputImage {
  file: File | null          // 本地上传的文件，优先使用
  preview: string            // 预览 URL（file 为 null 时用于重新上传）
  assetLocation: string      // 资产库中的存储路径（从资产库选择时有值）
}

export interface ImageGenerateParams {
  modelId: number
  prompt: string
  width: number
  height: number
  batchSize: number
  img2img: boolean           // true 表示图生图模式
  inputImages: InputImage[]  // 图生图时的参考图列表
  userId?: number
}

export interface ImageGenerateResult {
  taskId?: string    // 异步任务 id，有值时需轮询
  images?: string[]  // 同步返回时的图片 URL 列表
}

/**
 * 将输入图片上传到后端资产库，返回资产 id 列表。
 * 支持三种来源：本地 File 对象、资产库路径（重新获取后上传）、预览 URL（blob）。
 */
async function uploadInputImages(images: InputImage[], userId: number): Promise<number[]> {
  const ids: number[] = []
  for (const img of images) {
    if (img.file) {
      // 直接上传本地文件
      const uploaded = await uploadInputImage(img.file, userId)
      ids.push(uploaded.id)
    } else if (img.assetLocation) {
      // 从资产库路径重新获取文件后上传
      const filename = img.assetLocation.replace(/\\/g, '/').split('/').pop()!
      const res = await fetch(`/api/view?filename=${encodeURIComponent(filename)}&type=output`)
      const blob = await res.blob()
      const file = new File([blob], img.assetLocation, { type: blob.type })
      const uploaded = await uploadInputImage(file, userId)
      ids.push(uploaded.id)
    } else if (img.preview) {
      // 从预览 URL（blob URL）获取文件后上传
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
