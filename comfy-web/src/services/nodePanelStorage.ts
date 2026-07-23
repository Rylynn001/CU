// 节点面板持久化存储服务
//
// 后端 API 版本：所有数据通过 /api-proxy/node-boards/* 持久化。
// 数据格式由旧 localStorage 格式适配为后端表结构。

// 单个子面板快照
export interface PanelSnapshot {
  assetIds: number[]
  ratio: number
}

// 完整面板文档快照（兼容 NodePanel.vue 内部使用）
export interface NodePanelSnapshot {
  panels: PanelSnapshot[]
  updatedAt: number
}

// 工作区元数据
export interface BoardMeta {
  id: number
  name: string
  updatedAt: number
}

// ── 工具函数 ────────────────────────────────────────────────────────────────

function getUserId(): number | null {
  try {
    const user = JSON.parse(localStorage.getItem('user') || '')
    return user?.id ?? null
  } catch {
    return null
  }
}

async function apiFetch(path: string, init?: RequestInit) {
  const res = await fetch(`/api/api-proxy/${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

// ── 工作区列表 ───────────────────────────────────────────────────────────────

export async function listBoards(userId: number): Promise<BoardMeta[]> {
  const data = await apiFetch(`node-boards?user_id=${userId}`)
  return (data.boards ?? []).map((b: any) => ({
    id: b.id,
    name: b.name,
    updatedAt: b.updated_at ?? 0,
  }))
}

// ── 加载工作区（转 NodePanelSnapshot 格式）────────────────────────────────────

export async function loadBoard(boardId: number, userId: number): Promise<NodePanelSnapshot | null> {
  try {
    const b = await apiFetch(`node-boards/${boardId}?user_id=${userId}`)
    return {
      panels: [
        { assetIds: b.panel1_asset_ids ?? [], ratio: b.panel1_ratio ?? 1 },
        { assetIds: b.panel2_asset_ids ?? [], ratio: b.panel2_ratio ?? 1 },
        { assetIds: b.panel3_asset_ids ?? [], ratio: b.panel3_ratio ?? 1 },
      ],
      updatedAt: b.updated_at ?? 0,
    }
  } catch {
    return null
  }
}

// ── 保存工作区 ────────────────────────────────────────────────────────────────

export async function saveBoard(boardId: number, userId: number, snapshot: NodePanelSnapshot): Promise<void> {
  await apiFetch(`node-boards/${boardId}`, {
    method: 'PUT',
    body: JSON.stringify({
      user_id: userId,
      panels: snapshot.panels.map((p) => ({
        asset_ids: p.assetIds,
        ratio: p.ratio,
      })),
    }),
  })
}

// ── 新建工作区 ────────────────────────────────────────────────────────────────

export async function createBoard(userId: number, name: string): Promise<BoardMeta> {
  const data = await apiFetch('node-boards', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, name }),
  })
  return { id: data.id, name: data.name, updatedAt: data.updated_at ?? 0 }
}

// ── 重命名工作区 ──────────────────────────────────────────────────────────────

export async function renameBoard(boardId: number, userId: number, name: string): Promise<void> {
  await apiFetch(`node-boards/${boardId}`, {
    method: 'PATCH',
    body: JSON.stringify({ user_id: userId, name }),
  })
}

// ── 删除工作区 ────────────────────────────────────────────────────────────────

export async function deleteBoard(boardId: number, userId: number): Promise<void> {
  await apiFetch(`node-boards/${boardId}?user_id=${userId}`, { method: 'DELETE' })
}

// ── 保留旧接口（兼容其他可能引用的地方，实现为空操作）─────────────────────────

/** @deprecated 使用 loadBoard / saveBoard 代替 */
export async function saveNodePanel(_docId: string, _snapshot: NodePanelSnapshot): Promise<void> {}
/** @deprecated 使用 loadBoard 代替 */
export async function loadNodePanel(_docId: string): Promise<NodePanelSnapshot | null> { return null }
export const DEFAULT_DOC_ID = 'default'
