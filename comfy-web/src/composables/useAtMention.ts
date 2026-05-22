import { ref } from 'vue'
import type { Ref } from 'vue'

interface MediaItem {
  url: string
  type: 'image' | 'video'
}

/**
 * 处理提示词输入框中的 @ 提及功能。
 * 用户输入 @ 时弹出媒体列表，选择后插入 "@图1" / "@视频1" 等标签。
 * getText/setText: 读写提示词内容
 * getItems: 获取当前可引用的媒体列表
 * textareaRef: 提示词输入框的 ref，用于获取光标位置
 */
export function useAtMention(
  getText: () => string,
  setText: (v: string) => void,
  getItems: () => MediaItem[],
  textareaRef: Ref<{ textarea?: HTMLTextAreaElement } | null>,
) {
  const atMentionActive = ref(false)   // 是否显示 @ 选择弹窗
  const atMentionStartIdx = ref(-1)    // @ 符号在文本中的位置，用于替换
  const atMentionIndex = ref(-1)       // 当前键盘高亮的列表项索引

  // keyup 时检测 @ 触发和 Escape 关闭
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

  // keydown 时处理上下箭头导航和 Enter 确认选择
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

  // 将选中的媒体项插入到提示词中，替换 @ 符号
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

  // 关闭 @ 选择弹窗
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
