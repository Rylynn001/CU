import { ref } from 'vue'
import type { Ref } from 'vue'

interface MediaItem {
  url: string
  type: 'image' | 'video'
}

export function useAtMention(
  getText: () => string,
  setText: (v: string) => void,
  getItems: () => MediaItem[],
  textareaRef: Ref<{ textarea?: HTMLTextAreaElement } | null>,
) {
  const atMentionActive = ref(false)
  const atMentionStartIdx = ref(-1)
  const atMentionIndex = ref(-1)

  function onPromptKeyup(e: KeyboardEvent) {
    if (e.key === '@') {
      if (getItems().length === 0) return
      const textarea = textareaRef.value?.textarea
      if (!textarea) return
      atMentionStartIdx.value = textarea.selectionStart - 1
      atMentionActive.value = true
      atMentionIndex.value = -1
    } else if (e.key === 'Escape') {
      atMentionActive.value = false
    }
  }

  function onPromptKeydown(e: KeyboardEvent | Event) {
    if (!(e instanceof KeyboardEvent)) return
    if (!atMentionActive.value) return
    const count = getItems().length
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      atMentionIndex.value = (atMentionIndex.value + 1) % count
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      atMentionIndex.value = (atMentionIndex.value - 1 + count) % count
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (atMentionIndex.value >= 0) insertMention(atMentionIndex.value)
    }
  }

  function insertMention(idx: number) {
    const textarea = textareaRef.value?.textarea
    if (!textarea) return
    const items = getItems()
    const item = items[idx]
    const label = item.type === 'video' ? `@视频${idx + 1}` : `@图${idx + 1}`
    const start = atMentionStartIdx.value
    const text = getText()
    const before = text.slice(0, start)
    const after = text.slice(start + 1)
    setText(`${before}${label} ${after}`)
    atMentionActive.value = false
    atMentionIndex.value = -1
    textarea.focus()
  }

  function closeMention() {
    atMentionActive.value = false
  }

  return {
    atMentionActive,
    atMentionIndex,
    onPromptKeyup,
    onPromptKeydown,
    insertMention,
    closeMention,
  }
}
