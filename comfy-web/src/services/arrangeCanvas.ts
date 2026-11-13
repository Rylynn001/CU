// 自动排布改编自 Toonflow（MIT），见 THIRD_PARTY_NOTICES.md。
import { nextTick } from 'vue'
import type { useVueFlow } from '@vue-flow/core'
import { graphlib, layout } from '@dagrejs/dagre'

export async function arrangeCanvas(flow: ReturnType<typeof useVueFlow>, signal?: AbortSignal) {
  signal?.throwIfAborted()
  await nextTick()
  signal?.throwIfAborted()
  flow.updateNodeInternals(flow.getNodes.value.map(node => node.id))
  await nextTick()
  signal?.throwIfAborted()

  const nodes = flow.getNodes.value
  const snapshot = nodes.map(node => ({ id: node.id, position: { ...node.position } }))
  if (!nodes.length) return { snapshot, arranged: false }

  for (const node of nodes) {
    const { width, height } = node.dimensions
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw new Error(`节点 ${node.data?.label ?? node.id} 尚未完成尺寸测量，请等待节点显示后重试`)
    }
  }

  const widths = nodes.map(node => node.dimensions.width).sort((a, b) => a - b)
  const heights = nodes.map(node => node.dimensions.height).sort((a, b) => a - b)
  const nodeGap = Math.max(96, Math.min(160, heights[Math.floor(heights.length / 2)]! / 4))
  const rankGap = Math.max(160, Math.min(320, widths[Math.floor(widths.length / 2)]! / 2))
  const groupGap = Math.max(nodeGap, rankGap) * 1.5

  const graph = new graphlib.Graph()
  graph.setGraph({ rankdir: 'LR', rankalign: 'top', nodesep: nodeGap, ranksep: rankGap, edgesep: 32 })
  graph.setDefaultEdgeLabel(() => ({}))
  nodes.forEach(node => graph.setNode(node.id, { width: node.dimensions.width, height: node.dimensions.height }))
  flow.getEdges.value.forEach(edge => {
    if (edge.source !== edge.target) graph.setEdge(edge.source, edge.target)
  })

  // 以连通分组分行排布，保持每条流程完整。
  const groups = graphlib.alg.components(graph).map(ids => {
    const members = new Set(ids)
    const subgraph = graph.filterNodes(id => members.has(id))
    subgraph.setGraph({ ...graph.graph() })
    layout(subgraph)
    return { ids, graph: subgraph, width: subgraph.graph().width as number, height: subgraph.graph().height as number }
  })

  const { width, height } = flow.dimensions.value
  const aspectRatio = width > 0 && height > 0 ? Math.max(0.75, Math.min(2, width / height)) : 1.6
  const area = groups.reduce((sum, group) => sum + (group.width + groupGap) * (group.height + groupGap), 0)
  const rowWidth = Math.max(...groups.map(group => group.width), Math.sqrt(area * aspectRatio))
  const origin = { x: Math.min(...nodes.map(node => node.position.x)), y: Math.min(...nodes.map(node => node.position.y)) }

  let x = 0
  let y = 0
  let rowHeight = 0
  const positions = groups.flatMap(group => {
    if (x > 0 && x + group.width > rowWidth) {
      x = 0
      y += rowHeight + groupGap
      rowHeight = 0
    }
    const result = group.ids.map(id => {
      const node = group.graph.node(id)
      const position = { x: origin.x + x + node.x - node.width / 2, y: origin.y + y + node.y - node.height / 2 }
      if (!Number.isFinite(position.x) || !Number.isFinite(position.y)) throw new Error(`节点 ${id} 的排列位置无效`)
      return { id, position }
    })
    x += group.width + groupGap
    rowHeight = Math.max(rowHeight, group.height)
    return result
  })
  positions.forEach(({ id, position }) => flow.updateNode(id, { position }))
  await nextTick()
  signal?.throwIfAborted()
  await flow.fitView({ duration: 0 })
  return { snapshot, arranged: true }
}
