import { ref, computed } from 'vue'

export interface MediaPreview {
  url: string
  type: 'image' | 'video'
}

export interface AssetPreview extends MediaPreview {
  id: number
}

export function useInputMedia(
  onError: (msg: string) => void,
  maxImages = 9,
  maxVideos = 3,
  maxTotal = 12,
) {
  const inputFiles = ref<File[]>([])
  const inputPreviews = ref<MediaPreview[]>([])
  const selectedAssetIds = ref<number[]>([])
  const selectedAssetPreviews = ref<AssetPreview[]>([])

  const allMediaItems = computed<MediaPreview[]>(() => [
    ...inputPreviews.value,
    ...selectedAssetPreviews.value,
  ])

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

  function removeFile(index: number) {
    URL.revokeObjectURL(inputPreviews.value[index].url)
    inputFiles.value.splice(index, 1)
    inputPreviews.value.splice(index, 1)
  }

  function removeAsset(index: number) {
    selectedAssetIds.value.splice(index, 1)
    selectedAssetPreviews.value.splice(index, 1)
  }

  function clearAllInputs() {
    inputPreviews.value.forEach(p => URL.revokeObjectURL(p.url))
    inputFiles.value = []
    inputPreviews.value = []
    selectedAssetIds.value = []
    selectedAssetPreviews.value = []
  }

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
      const filename = asset.location.replace(/\\/g, '/').split('/').pop()!
      selectedAssetPreviews.value.push({
        id: asset.id,
        url: `/api/view?filename=${encodeURIComponent(filename)}&type=output`,
        type: isVideo ? 'video' : 'image',
      })
    }
  }

  // 编辑器相关：将资产转为本地文件（编辑后从资产列表移除，加入本地文件列表）
  function replaceAssetWithFile(index: number, file: File) {
    selectedAssetIds.value.splice(index, 1)
    selectedAssetPreviews.value.splice(index, 1)
    inputFiles.value.push(file)
    inputPreviews.value.push({ url: URL.createObjectURL(file), type: 'image' })
  }

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
