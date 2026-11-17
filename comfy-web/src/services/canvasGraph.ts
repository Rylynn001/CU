// 端口协议及连接校验改编自 Toonflow（MIT），见 THIRD_PARTY_NOTICES.md。
import type { InjectionKey, Ref } from 'vue'
import type { Connection } from '@vue-flow/core'
import type { ApiModel } from '../api/apiService'

export type CanvasParameterValue = string | number | boolean

export type MediaType = 'IMAGE' | 'VIDEO' | 'STRING'
export interface CanvasHandle {
  id: string
  type: 'source' | 'target'
  dataType: MediaType | MediaType[]
  label: string
}
export interface CanvasNodeData {
  width?: number
  height?: number
  label: string
  prompt: string
  model: string
  parameters: Record<string, CanvasParameterValue>
  inputAssetIds?: number[]
  executionId?: string
  /** 兼容已保存的旧画布；新节点只使用 parameters。 */
  ratio?: string
  quality?: string
  resolution?: string
  duration?: number
  n?: number
  handles: CanvasHandle[]
  outputs: Record<string, { dataType: MediaType; value: { assetIds: number[] } | string }>
  task?: { taskId: string; historyId: number; state: 'pending' | 'completed' | 'failed'; error?: string }
}
export interface CanvasNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: CanvasNodeData
  selected?: boolean
}
export interface CanvasEdge {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
  type?: string
  selected?: boolean
}
export interface CanvasAsset { id: number; url: string; type: 'image' | 'video' }
export interface CanvasReference extends CanvasAsset { label: string; mention: string; referenceId: number }

export function canvasReferences(nodes: CanvasNode[], assets: Record<number, CanvasAsset>, edges?: CanvasEdge[], targetId?: string): CanvasReference[] {
  const seen = new Set<number>()
  const counters = { image: 0, video: 0 }
  const sources = edges
    ? edges.filter(edge => edge.target === targetId).map(edge => ({ node: nodes.find(node => node.id === edge.source), port: edge.sourceHandle }))
    : nodes.map(node => ({ node, port: undefined }))
  return sources.flatMap(({ node, port }) => {
    if (!node || node.data.task?.state === 'pending') return []
    const outputs = port ? [node.data.outputs[port]] : Object.values(node.data.outputs)
    return outputs.flatMap(output => {
      if (!output || typeof output.value === 'string') return []
      return output.value.assetIds.flatMap(id => {
        if (seen.has(id)) return []
        seen.add(id)
        const type = output.dataType === 'VIDEO' ? 'video' : 'image'
        counters[type] += 1
        return [{ id, url: assets[id]?.url ?? '', type, label: node.data.label, referenceId: counters[type], mention: `@${type === 'video' ? '视频' : '图片'}${counters[type]}` } satisfies CanvasReference]
      })
    })
  })
}
export const nodeKinds = [
  { type: 'remote-imageGenerationNode', label: '图片生成', output: 'IMAGE' },
  { type: 'remote-videoGenerationNode', label: '视频生成', output: 'VIDEO' },
  { type: 'remote-textNode', label: '文本', output: 'STRING' },
  { type: 'remote-imageNode', label: '图片素材', output: 'IMAGE' },
  { type: 'remote-videoNode', label: '视频素材', output: 'VIDEO' },
] as const

export function makeNode(type: string, position: { x: number; y: number }): CanvasNode {
  const kind = nodeKinds.find(item => item.type === type) ?? nodeKinds[0]
  const generating = type.includes('Generation')
  const port = kind.output === 'STRING' ? 'text' : kind.output.toLowerCase()
  const handles: CanvasHandle[] = []
  if (generating) handles.push({ id: 'in', type: 'target', dataType: kind.output === 'IMAGE' ? ['IMAGE', 'STRING'] : ['IMAGE', 'VIDEO', 'STRING'], label: '参考素材、文本输入' })
  handles.push({ id: port, type: 'source', dataType: kind.output, label: `${kind.label}输出` })
  return {
    id: crypto.randomUUID(), type, position,
    data: { label: kind.label, prompt: '', model: '', parameters: {}, handles, outputs: {} },
  }
}

export function validConnection(connection: Connection & { id?: string }, nodes: CanvasNode[], edges: CanvasEdge[]): boolean {
  if (connection.source === connection.target) return false
  const source = nodes.find(node => node.id === connection.source)?.data?.handles.find(handle => handle.id === connection.sourceHandle && handle.type === 'source')
  const target = nodes.find(node => node.id === connection.target)?.data?.handles.find(handle => handle.id === connection.targetHandle && handle.type === 'target')
  if (!source || !target) return false
  const sourceTypes = Array.isArray(source.dataType) ? source.dataType : [source.dataType]
  const targetTypes = Array.isArray(target.dataType) ? target.dataType : [target.dataType]
  if (!sourceTypes.some(type => targetTypes.includes(type))) return false
  if (edges.some(edge => edge.id !== connection.id && edge.source === connection.source && edge.target === connection.target && edge.sourceHandle === connection.sourceHandle && edge.targetHandle === connection.targetHandle)) return false
  // 阻止环路，保证引用关系可以沿上游解释。
  const pending = [connection.target]
  const seen = new Set<string>()
  while (pending.length) {
    const id = pending.pop()!
    if (id === connection.source) return false
    if (seen.has(id)) continue
    seen.add(id)
    edges.filter(edge => edge.source === id).forEach(edge => pending.push(edge.target))
  }
  return true
}

export function collectInputs(nodeId: string, nodes: CanvasNode[], edges: CanvasEdge[]) {
  const assetIds: number[] = []
  const texts: string[] = []
  for (const edge of edges.filter(edge => edge.target === nodeId)) {
    const node = nodes.find(item => item.id === edge.source)
    const output = node?.data?.outputs[edge.sourceHandle ?? '']
    if (!output) throw new Error(`“${node?.data?.label ?? '上游节点'}”暂无输出，请先生成或选择素材`)
    if (node?.data?.task?.state === 'pending') throw new Error('上游节点正在生成，请等待完成')
    if (typeof output.value === 'string') texts.push(output.value)
    else assetIds.push(...output.value.assetIds)
  }
  return { assetIds: [...new Set(assetIds)], texts }
}

export interface CanvasActions {
  isSubmitting: (id: string) => boolean
  assets: Ref<Record<number, CanvasAsset>>
  imageModels: Ref<ApiModel[]>
  videoModels: Ref<ApiModel[]>
  setModel: (id: string, model: string) => void
  run: (id: string) => void
  pick: (id: string) => void
  duplicate: (id: string) => void
  remove: (id: string) => void
}
export const canvasActionsKey: InjectionKey<CanvasActions> = Symbol('canvasActions')
