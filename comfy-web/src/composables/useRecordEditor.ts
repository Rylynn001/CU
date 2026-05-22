import { ref } from 'vue'
import type { Ref } from 'vue'
import type ImageEditor from '../components/ImageEditor.vue'

interface RecordWithImages {
  id: string
  status: string
  prompt: string
  images?: string[]
  videoUrl?: string
  inputAssetUrls?: Array<{ url: string; type: string }>
}

/**
 * 管理历史记录的"再次编辑"弹窗状态。
 * 点击某条历史记录的编辑按钮时，打开弹窗并预填充提示词和图片。
 * inlineEditorRef: 弹窗内嵌的 ImageEditor 组件 ref，用于获取编辑后的图片文件
 */
export function useRecordEditor(
  inlineEditorRef: Ref<InstanceType<typeof ImageEditor> | null>,
) {
  const showRecordEditor = ref(false)          // 是否显示编辑弹窗
  const editingRecordId = ref('')              // 当前编辑的记录 id
  const recordEditorPrompt = ref('')           // 弹窗中的提示词
  const recordEditorImages = ref<string[]>([]) // 弹窗中展示的输出图片列表
  const recordEditorInputUrls = ref<Array<{ url: string; type: string }>>([]) // 输入素材列表
  const recordEditorEditedFile = ref<File | null>(null)   // 用户在编辑器中修改后的图片文件
  const recordEditorEditedPreview = ref('')               // 编辑后图片的预览 URL
  const recordEditorEditingSrc = ref('')                  // 当前在图片编辑器中打开的图片 URL
  const showRecordImageEditor = ref(false)                // 是否显示图片编辑器

  // 打开编辑弹窗，预填充记录内容；优先用输入图作为编辑器初始图
  function openEditor(rec: RecordWithImages) {
    editingRecordId.value = rec.id
    recordEditorPrompt.value = rec.prompt
    recordEditorImages.value = rec.images || []
    recordEditorInputUrls.value = rec.inputAssetUrls || []
    recordEditorEditedFile.value = null
    recordEditorEditedPreview.value = ''
    showRecordEditor.value = true

    // 优先用输入图，其次用输出图作为编辑器初始图
    const firstInputImg = (rec.inputAssetUrls || []).find(a => a.type !== 'video')
    const firstSrc = firstInputImg?.url || rec.images?.[0] || ''
    if (firstSrc) {
      recordEditorEditingSrc.value = firstSrc
      showRecordImageEditor.value = true
    }
  }

  // 在弹窗内切换编辑另一张图片
  function openRecordImageEditor(src: string) {
    recordEditorEditingSrc.value = src
    showRecordImageEditor.value = true
  }

  // 图片编辑器确认：保存编辑后的文件并生成预览 URL
  function onImageEditorConfirm(file: File) {
    recordEditorEditedFile.value = file
    recordEditorEditedPreview.value = URL.createObjectURL(file)
    showRecordImageEditor.value = false
  }

  // 图片编辑器取消：关闭编辑器，不保存
  function onImageEditorCancel() {
    showRecordImageEditor.value = false
  }

  // 关闭编辑弹窗
  function closeEditor() {
    showRecordEditor.value = false
  }

  // 获取最终要提交的图片文件：优先从内嵌编辑器 canvas 导出，其次用已保存的文件
  async function getEditedFile(): Promise<File | null> {
    if (inlineEditorRef.value) {
      const canvasFile = await inlineEditorRef.value.getFile()
      if (canvasFile) return canvasFile
    }
    return recordEditorEditedFile.value
  }

  return {
    showRecordEditor,
    editingRecordId,
    recordEditorPrompt,
    recordEditorImages,
    recordEditorInputUrls,
    recordEditorEditedFile,
    recordEditorEditedPreview,
    recordEditorEditingSrc,
    showRecordImageEditor,
    openEditor,
    openRecordImageEditor,
    onImageEditorConfirm,
    onImageEditorCancel,
    closeEditor,
    getEditedFile,
  }
}
