import { ref, computed } from 'vue'

export interface MediaPreview {
  url: string
  type: 'image' | 'video'
}

export interface AssetPreview extends MediaPreview {
  id: number  // 资产库中的 id，提交时传给后端
}

/**
 * 管理生成任务的输入素材（本地上传文件 + 从资产库选择的素材）。
 * onError: 超出数量限制时的错误回调
 * maxImages/maxVideos/maxTotal: 各类型和总数上限
 */
export function useInputMedia(
  onError: (msg: string) => void,
  maxImages = 9,
  maxVideos = 3,
  maxTotal = 12,
) {
  const inputFiles = ref<File[]>([])                      // 本地上传的文件对象
  const inputPreviews = ref<MediaPreview[]>([])           // 本地上传文件的预览 URL
  const selectedAssetIds = ref<number[]>([])              // 从资产库选中的素材 id 列表
  const selectedAssetPreviews = ref<AssetPreview[]>([])   // 从资产库选中的素材预览

  // 合并本地上传和资产库素材，供 @ 提及功能使用
  const allMediaItems = computed<MediaPreview[]>(() => [
    ...inputPreviews.value,
    ...selectedAssetPreviews.value,
  ])

  // 处理文件选择（input[type=file] 的 change 事件）
  // 过滤非图片/视频文件，校验数量上限后追加到列表
  function handleFilesChange(files: FileList | null) {
    if (!files || files.length === 0) return
    const newFiles: File[] = []
    const newPreviews: MediaPreview[] = []

    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      const isVideo = file.type.startsWith('video/')
      const isImage = file.type.startsWith('image/')
      if (!isVideo && !isImage) continue
      newFiles.push(file)
      newPreviews.push({ url: URL.createObjectURL(file), type: isVideo ? 'video' : 'image' })
    }

    const totalImages = [...inputPreviews.value, ...newPreviews].filter(p => p.type === 'image').length
    const totalVideos = [...inputPreviews.value, ...newPreviews].filter(p => p.type === 'video').length
    const total = inputFiles.value.length + newFiles.length + selectedAssetIds.value.length

    if (totalImages > maxImages) { onError(`最多只能上传 ${maxImages} 张图片`); return }
    if (totalVideos > maxVideos) { onError(`最多只能上传 ${maxVideos} 个视频`); return }
    if (total > maxTotal) { onError(`最多只能上传 ${maxTotal} 个素材`); return }

    inputFiles.value.push(...newFiles)
    inputPreviews.value.push(...newPreviews)
  }

  // 移除本地上传的文件，同时释放 Object URL 避免内存泄漏
  function removeFile(index: number) {
    URL.revokeObjectURL(inputPreviews.value[index].url)
    inputFiles.value.splice(index, 1)
    inputPreviews.value.splice(index, 1)
  }

  // 移除从资产库选中的素材
  function removeAsset(index: number) {
    selectedAssetIds.value.splice(index, 1)
    selectedAssetPreviews.value.splice(index, 1)
  }

  // 清空所有输入素材，释放所有 Object URL
  function clearAllInputs() {
    inputPreviews.value.forEach(p => URL.revokeObjectURL(p.url))
    inputFiles.value = []
    inputPreviews.value = []
    selectedAssetIds.value = []
    selectedAssetPreviews.value = []
  }

  // 从资产库选择素材，过滤已选中的，校验数量上限后追加
  function handleAssetSelect(assets: Array<{ id: number; location: string; asset_type?: string }>) {
    const newAssets = assets.filter(a => !selectedAssetIds.value.includes(a.id))

    const totalImages = [
      ...inputPreviews.value.filter(p => p.type === 'image'),
      ...selectedAssetPreviews.value.filter(p => p.type === 'image'),
      ...newAssets.filter(a => a.asset_type === 'picture'),
    ].length
    const totalVideos = [
      ...inputPreviews.value.filter(p => p.type === 'video'),
      ...selectedAssetPreviews.value.filter(p => p.type === 'video'),
      ...newAssets.filter(a => a.asset_type === 'video'),
    ].length
    const total = inputFiles.value.length + selectedAssetIds.value.length + newAssets.length

    if (totalImages > maxImages) { onError(`最多只能选择 ${maxImages} 张图片`); return }
    if (totalVideos > maxVideos) { onError(`最多只能选择 ${maxVideos} 个视频`); return }
    if (total > maxTotal) { onError(`最多只能选择 ${maxTotal} 个素材`); return }

    for (const asset of newAssets) {
      selectedAssetIds.value.push(asset.id)
      const isVideo = asset.asset_type === 'video'
      // 如果 location 是完整 URL（包含 /api/），直接使用；否则构造 /api/view URL
      const previewUrl = asset.location.includes('/api/')
        ? asset.location
        : `/api/view?filename=${encodeURIComponent(asset.location.replace(/\\/g, '/').split('/').pop()!)}&type=output`
      selectedAssetPreviews.value.push({
        id: asset.id,
        url: previewUrl,
        type: isVideo ? 'video' : 'image',
      })
    }
  }

  // 将资产库素材替换为本地编辑后的文件（编辑器修改后调用）
  function replaceAssetWithFile(index: number, file: File) {
    selectedAssetIds.value.splice(index, 1)
    selectedAssetPreviews.value.splice(index, 1)
    inputFiles.value.push(file)
    inputPreviews.value.push({ url: URL.createObjectURL(file), type: 'image' })
  }

  // 替换本地上传列表中某个文件（编辑器修改后调用）
  function replaceFile(index: number, file: File) {
    URL.revokeObjectURL(inputPreviews.value[index].url)
    inputFiles.value[index] = file
    inputPreviews.value[index] = { url: URL.createObjectURL(file), type: 'image' }
  }

  return {
    inputFiles,
    inputPreviews,
    selectedAssetIds,
    selectedAssetPreviews,
    allMediaItems,
    handleFilesChange,
    removeFile,
    removeAsset,
    clearAllInputs,
    handleAssetSelect,
    replaceFile,
    replaceAssetWithFile,
  }
}
