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

export function useRecordEditor(
  inlineEditorRef: Ref<InstanceType<typeof ImageEditor> | null>,
) {
  const showRecordEditor = ref(false)
  const editingRecordId = ref('')
  const recordEditorPrompt = ref('')
  const recordEditorImages = ref<string[]>([])
  const recordEditorInputUrls = ref<Array<{ url: string; type: string }>>([])
  const recordEditorEditedFile = ref<File | null>(null)
  const recordEditorEditedPreview = ref('')
  const recordEditorEditingSrc = ref('')
  const showRecordImageEditor = ref(false)

  function openEditor(rec: RecordWithImages) {
    editingRecordId.value = rec.id
    recordEditorPrompt.value = rec.prompt
    recordEditorImages.value = rec.images || []
    recordEditorInputUrls.value = rec.inputAssetUrls || []
    recordEditorEditedFile.value = null
    recordEditorEditedPreview.value = ''
    showRecordEditor.value = true

    // 优先用输入图，其次用输出图
    const firstInputImg = (rec.inputAssetUrls || []).find(a => a.type !== 'video')
    const firstSrc = firstInputImg?.url || rec.images?.[0] || ''
    if (firstSrc) {
      recordEditorEditingSrc.value = firstSrc
      showRecordImageEditor.value = true
    }
  }

  function openRecordImageEditor(src: string) {
    recordEditorEditingSrc.value = src
    showRecordImageEditor.value = true
  }

  function onImageEditorConfirm(file: File) {
    recordEditorEditedFile.value = file
    recordEditorEditedPreview.value = URL.createObjectURL(file)
    showRecordImageEditor.value = false
  }

  function onImageEditorCancel() {
    showRecordImageEditor.value = false
  }

  function closeEditor() {
    showRecordEditor.value = false
  }

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
