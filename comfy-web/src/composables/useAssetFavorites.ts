import { reactive } from 'vue'

export type FavoriteTag = 0 | 1 | 2 | 3 | 4

const favoriteTags = reactive(new Map<number, FavoriteTag>())

export function setAssetFavoriteTag(assetId: number, tag: FavoriteTag) {
  favoriteTags.set(assetId, tag)
}

export function cacheAssetFavoriteTags(assets: Array<{ id: number; tag?: number }>) {
  for (const asset of assets) {
    setAssetFavoriteTag(asset.id, (asset.tag || 0) as FavoriteTag)
  }
}

export async function loadAssetFavoriteTags(assetIds: number[]) {
  const ids = [...new Set(assetIds.filter(Boolean))]
  if (!ids.length) return

  try {
    const res = await fetch('/api/api-proxy/assets/by-ids', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    })
    if (!res.ok) return
    const data = await res.json()
    cacheAssetFavoriteTags(data.assets || [])
  } catch {
    // 收藏状态加载失败时不阻断历史记录展示
  }
}

export function getAssetFavoriteTag(assetId?: number): FavoriteTag {
  return assetId ? favoriteTags.get(assetId) || 0 : 0
}
