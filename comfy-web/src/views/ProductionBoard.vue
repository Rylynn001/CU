<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Handle, Position, VueFlow, useVueFlow, type Edge, type Node, type NodeChange, type NodeDragEvent, type NodeMouseEvent } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import {
  ArrowDown, ArrowUp, Close, EditPen, FolderAdd, FolderOpened, Lock, MoreFilled, Picture,
  Plus, Pointer, Search, Star, Unlock, Upload, VideoCamera,
} from '@element-plus/icons-vue'
import MediaViewer, { type MediaViewerItem } from '../components/MediaViewer.vue'
import LayerBackdrop from '../components/LayerBackdrop.vue'
import BoardMinimap from '../components/BoardMinimap.vue'
import { analyzeImageColors, getDominantColors } from '../utils/imageColors'
import { getApiModels, pollTaskUntilDone } from '../api/apiService'
import { submitImageGeneration, type InputImage } from '../services/imageGenerationService'
import { submitImg2VideoGeneration, submitVideoGeneration } from '../services/videoGenerationService'
import { getCurrentUserId } from '../utils/user'

type MediaType = 'image' | 'video'
type ReferenceSource = 'canvas' | 'group' | 'asset' | 'upload'

interface ReferenceInput {
  id: string
  source: ReferenceSource
  type: MediaType
  title: string
  src: string
}

interface ModelCapability {
  id: 'smart' | 'quality' | 'fast'
  label: string
  inputLimit: number
  modes: MediaType[]
}

interface CreationDraft {
  mode: MediaType
  prompt: string
  references: ReferenceInput[]
  modelId: ModelCapability['id']
  ratio: string
  generationCount: 1 | 2 | 4
  quality: string
  creativity: number
  promptWeight: number
  seed: number
  negativePrompt: string
}

interface MediaVersion {
  id: string
  type: MediaType
  title: string
  src: string
  prompt: string
  status: 'generating' | 'done' | 'error'
  error?: string
}

interface GenerationBatch {
  id: string
  versions: MediaVersion[]
  adoptedVersionId?: string
}

type SourceRef =
  | { kind: 'card'; cardId: number; layerId?: string }
  | { kind: 'group-output'; groupId: number; outputId: string; layerId?: string }

interface CreationCard {
  kind: 'creation'
  id: number
  source?: SourceRef
  title: string
  x: number
  y: number
  activeVersionId: string
  batches: GenerationBatch[]
  draft: CreationDraft
}

interface GroupOutput {
  id: string
  name: string
  cardIds: number[]
}

interface GroupInputNode {
  kind: 'input'
  id: number
  x: number
  y: number
  name: string
}

interface GroupOutputNode {
  kind: 'output'
  id: number
  x: number
  y: number
  outputId: string
}

interface GroupBoundaryLink {
  direction: 'incoming' | 'outgoing'
  targetCardId: number
  source: SourceRef
}

interface GroupCard {
  kind: 'group'
  id: number
  title: string
  x: number
  y: number
  children: CreationCard[]
  groups: GroupCard[]
  inputNodes: GroupInputNode[]
  outputNodes: GroupOutputNode[]
  outputs: GroupOutput[]
  defaultOutputId?: string
  incomingSources: SourceRef[]
  viewport: { x: number; y: number; zoom: number }
  viewportReady: boolean
  boundaryLinks: GroupBoundaryLink[]
  sharing: 'personal' | 'team'
}

type BoardItem = CreationCard | GroupCard | GroupInputNode | GroupOutputNode

interface TextAnnotation {
  kind: 'text'
  id: number
  x: number
  y: number
  text: string
}

interface BrushAnnotation {
  kind: 'brush'
  id: number
  x: number
  y: number
  width: number
  height: number
  path: string
}

type CanvasAnnotation = TextAnnotation | BrushAnnotation
type CanvasItem = BoardItem | CanvasAnnotation

interface BoardLayer {
  id: string
  name: string
  visible: boolean
  locked: boolean
  rootSteps: CreationCard[]
  groups: GroupCard[]
  annotations: CanvasAnnotation[]
  draft: CreationDraft
  viewport: { x: number; y: number; zoom: number }
}

interface PendingDecision {
  sourceCardId: number
  targetCardId: number
  batch: GenerationBatch
  selectedVersionId?: string
}

const MAX_REFERENCE_INPUTS = 100
const MAX_CONNECTIONS = 1_200
const BOARD_SNAPSHOT_VERSION = 2
const COLOR_DRIFT = .3
const MAINLINE_WEIGHT = .3
const NEUTRAL_LINE_COLOR = { red: 214, green: 214, blue: 214 }
const STEP_WIDTH = 286
const STEP_HEIGHT = 164
const STEP_GAP = 350
const MAX_IMAGE_DIMENSION = 16_384
const TRAIL_FADE_LENGTH = 520
const TRAIL_PORT_GAP = 8
const route = useRoute()
const boardId = String(route.query.board || localStorage.getItem('production-board-id') || crypto.randomUUID())
if (!route.query.board) localStorage.setItem('production-board-id', boardId)
const boardClientId = crypto.randomUUID()
const saveState = ref<'saved' | 'saving' | 'local' | 'error'>('saved')
let saveTimer = 0
let boardSocket: WebSocket | undefined
let applyingRemoteState = false
const MODEL_CAPABILITIES: ModelCapability[] = [
  { id: 'smart', label: '智能匹配', inputLimit: 100, modes: ['image', 'video'] },
  { id: 'quality', label: '质量优先', inputLimit: 16, modes: ['image'] },
  { id: 'fast', label: '快速生成', inputLimit: 4, modes: ['video'] },
]
const imageA = 'https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=900&q=85'
const imageB = 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=900&q=85'
const videoA = 'https://storage.googleapis.com/coverr-main/mp4/Mt_Baker.mp4'

function initialDraft(mode: MediaType, prompt: string, reference?: ReferenceInput): CreationDraft {
  return {
    mode,
    prompt,
    references: reference ? [reference] : [],
    modelId: 'smart',
    ratio: '16:9',
    generationCount: 1,
    quality: 'standard',
    creativity: 65,
    promptWeight: 75,
    seed: -1,
    negativePrompt: '',
  }
}

function initialBatch(version: MediaVersion): GenerationBatch {
  return { id: crypto.randomUUID(), versions: [version], adoptedVersionId: version.id }
}

const characterVersion: MediaVersion = { id: 'version-character', type: 'image', title: '角色设定 · 主角', src: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=900&q=85', prompt: '电影角色设定图，年轻女性主角，坚定目光，暖灰色服装，工作室肖像', status: 'done' }
const turnaroundVersion: MediaVersion = { id: 'version-turnaround', type: 'image', title: '角色三视图', src: 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=900&q=85', prompt: '同一角色三视图，正面、侧面、背面，统一光线与比例', status: 'done' }
const costumeVersion: MediaVersion = { id: 'version-costume', type: 'image', title: '服装与道具', src: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=900&q=85', prompt: '角色服装细节设计，旅行夹克、旧相机与随身背包，材质参考', status: 'done' }
const moodVersion: MediaVersion = { id: 'version-mood', type: 'image', title: '场景氛围参考', src: imageA, prompt: '荒野公路，黄昏暖光，远处山脉，低机位电影感构图', status: 'done' }
const layoutVersion: MediaVersion = { id: 'version-layout', type: 'image', title: '场景构图草案', src: imageB, prompt: '角色站在公路前景，远处山脉和日落，明确前中后景层次', status: 'done' }
const compositionVersion: MediaVersion = { ...layoutVersion, id: 'version-layout-composition', title: '场景构图 · 定稿' }
const finalSceneVersion: MediaVersion = { id: 'version-final-scene', type: 'image', title: '最终场景 · 黄昏出发', src: 'https://images.unsplash.com/photo-1493246507139-91e8fad9978e?auto=format&fit=crop&w=900&q=85', prompt: '电影感最终场景，角色在黄昏荒野中出发，暖色天空、深色山脉、广角构图', status: 'done' }

const initialRootSteps: CreationCard[] = [
  { kind: 'creation', id: 1, title: '角色设定', x: 80, y: 120, activeVersionId: characterVersion.id, batches: [initialBatch(characterVersion)], draft: initialDraft('image', characterVersion.prompt) },
  { kind: 'creation', id: 2, source: { kind: 'card', cardId: 1 }, title: '角色三视图', x: 430, y: 55, activeVersionId: turnaroundVersion.id, batches: [initialBatch(turnaroundVersion)], draft: initialDraft('image', turnaroundVersion.prompt, { id: 'canvas-version-character', source: 'canvas', type: 'image', title: characterVersion.title, src: characterVersion.src }) },
  { kind: 'creation', id: 3, source: { kind: 'card', cardId: 1 }, title: '服装与道具', x: 430, y: 300, activeVersionId: costumeVersion.id, batches: [initialBatch(costumeVersion)], draft: initialDraft('image', costumeVersion.prompt, { id: 'canvas-version-character-costume', source: 'canvas', type: 'image', title: characterVersion.title, src: characterVersion.src }) },
  { kind: 'creation', id: 4, source: { kind: 'card', cardId: 3 }, title: '场景氛围', x: 780, y: 55, activeVersionId: moodVersion.id, batches: [initialBatch(moodVersion)], draft: initialDraft('image', moodVersion.prompt, { id: 'canvas-version-costume-mood', source: 'canvas', type: 'image', title: costumeVersion.title, src: costumeVersion.src }) },
  { kind: 'creation', id: 5, source: { kind: 'card', cardId: 3 }, title: '角色进入场景', x: 780, y: 300, activeVersionId: layoutVersion.id, batches: [initialBatch(layoutVersion)], draft: initialDraft('image', layoutVersion.prompt, { id: 'canvas-version-costume', source: 'canvas', type: 'image', title: costumeVersion.title, src: costumeVersion.src }) },
  { kind: 'creation', id: 6, source: { kind: 'card', cardId: 5 }, title: '场景构图', x: 1130, y: 300, activeVersionId: compositionVersion.id, batches: [initialBatch(compositionVersion)], draft: initialDraft('image', compositionVersion.prompt, { id: 'canvas-version-layout', source: 'canvas', type: 'image', title: layoutVersion.title, src: layoutVersion.src }) },
  { kind: 'creation', id: 7, source: { kind: 'card', cardId: 6 }, title: '最终场景', x: 1480, y: 300, activeVersionId: finalSceneVersion.id, batches: [initialBatch(finalSceneVersion)], draft: initialDraft('image', finalSceneVersion.prompt, { id: 'canvas-version-final-layout', source: 'canvas', type: 'image', title: layoutVersion.title, src: layoutVersion.src }) },
]
const testVersionTemplates = [characterVersion, turnaroundVersion, costumeVersion, moodVersion, layoutVersion, compositionVersion, finalSceneVersion]
function createTestCards(startId: number, count: number, layerIndex: number): CreationCard[] {
  return Array.from({ length: count }, (_, index) => {
    const id = startId + index
    const template = testVersionTemplates[(id - 1) % testVersionTemplates.length]
    const version: MediaVersion = { ...template, id: `test-version-${id}`, title: `L${layerIndex + 1} · 节点 ${index + 1}` }
    return {
      kind: 'creation',
      id,
      source: index > 0 ? { kind: 'card', cardId: id - 1 } : undefined,
      title: version.title,
      x: 90 + (index % 10) * 330 + layerIndex * 24,
      y: 70 + Math.floor(index / 10) * 210 + layerIndex * 18,
      activeVersionId: version.id,
      batches: [initialBatch(version)],
      draft: initialDraft('image', template.prompt),
    }
  })
}
const testLayers: BoardLayer[] = Array.from({ length: 5 }, (_, layerIndex) => ({
  id: crypto.randomUUID(),
  name: `画板 ${layerIndex + 1}`,
  visible: true,
  locked: false,
  rootSteps: createTestCards(layerIndex * 180 + 1, 180, layerIndex),
  groups: [],
  annotations: [],
  draft: initialDraft('image', ''),
  viewport: { x: 0, y: 0, zoom: 1 },
}))
const layers = ref<BoardLayer[]>(testLayers)
const activeLayerId = ref(layers.value[4].id)
const renderedLayerId = ref(activeLayerId.value)
const layerSwitching = ref(false)
const handoffLayerId = ref<string | null>(null)
const handoffFading = ref(false)
const handoffViewport = ref({ x: 0, y: 0, zoom: 1 })
const transitionDirection = ref<'up' | 'down'>('up')
const TRANSITION_MS = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220
let handoffTimer = 0
let handoffFallbackTimer = 0
let handoffReleaseArmed = false
let handoffReleaseScheduled = false
let pendingHandoffMedia = new Set<string>()
const currentLayer = computed(() => layers.value.find(layer => layer.id === activeLayerId.value) ?? layers.value[0])
const renderedLayer = computed(() => layers.value.find(layer => layer.id === renderedLayerId.value) ?? currentLayer.value)
const rootSteps = computed<CreationCard[]>({ get: () => currentLayer.value.rootSteps, set: value => { currentLayer.value.rootSteps = value } })
const groups = computed<GroupCard[]>({ get: () => currentLayer.value.groups, set: value => { currentLayer.value.groups = value } })
const annotations = computed<CanvasAnnotation[]>({ get: () => currentLayer.value.annotations, set: value => { currentLayer.value.annotations = value } })
const assets = [
  { type: 'image' as const, title: '星夜', src: 'https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=500&q=80' },
  { type: 'image' as const, title: '山野', src: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=500&q=80' },
  { type: 'image' as const, title: '人物', src: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=500&q=80' },
  { type: 'image' as const, title: '空间', src: 'https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=500&q=80' },
  { type: 'video' as const, title: '海岸镜头', src: videoA },
]

const activeStepId = ref(layers.value[4].rootSteps[0].id)
const focusedStepId = ref<number | null>(layers.value[4].rootSteps[0].id)
const focusedGroupId = ref<number | null>(null)
const activeGroupId = ref<number | null>(null)
const groupStack = ref<GroupCard[]>([])
const isCanvasMoving = ref(false)
const canvasElement = ref<HTMLElement>()
const layerPanelElement = ref<HTMLElement>()
const assetPanelElement = ref<HTMLElement>()
const layerPanelPosition = ref<{ left: number; top: number } | null>(null)
const assetPanelPosition = ref<{ left: number; top: number } | null>(null)
const layerContextMenu = ref<{ layerId: string; x: number; y: number } | null>(null)
const renamingLayerId = ref<string | null>(null)
let layerPanelDrag: { offsetX: number; offsetY: number } | null = null
let assetPanelDrag: { offsetX: number; offsetY: number } | null = null
const canvasSize = ref({ width: 0, height: 0 })
const boardViewport = ref({ x: 0, y: 0, zoom: 1 })
const hasSavedBoardViewport = ref(false)
const backdropBlurEnabled = !new URLSearchParams(window.location.search).has('noBlur')
let canvasResizeObserver: ResizeObserver | undefined
const selectedItemIds = ref<number[]>([])
const rootViewport = ref({ x: 0, y: 0, zoom: 1 })
const groupMessage = ref('')
let groupCount = 0
let selectionBaseIds: number[] = []
let additiveCanvasSelection = false
let brushPoints: Array<{ x: number; y: number }> = []
const canvasTool = ref<'select' | 'brush'>('select')
const flow = useVueFlow('production-board')
const pendingDecision = ref<PendingDecision | null>(null)
const historyStepId = ref<number | null>(null)
const historySelectedVersionId = ref<string>()
const controlsOpen = ref(true)
const assetFixed = ref(true)
const advancedOpen = ref(false)
const referencePickerOpen = ref(false)
const assetsOpen = ref(true)
const mobileAssetsOpen = ref(false)
type AssetLibraryFilter = 'all' | MediaType | 'reference-set' | 'process-set' | 'personal' | 'team'
const assetFilter = ref<AssetLibraryFilter>('all')
const assetSearch = ref('')
const selectedAsset = ref<(typeof assets)[number]>(assets[0])
const selectedCollectionId = ref<number | null>(null)
const previewVersion = ref<MediaVersion | null>(null)
const snapshotsOpen = ref(false)
const snapshots = ref<Array<{ id: number; name: string; created_at: string }>>([])
const uploadedUrls = new Set<string>()
const sourceColors = ref<Record<string, RgbColor>>({})
const sourceColorRequests = new Map<string, Promise<RgbColor | undefined>>()

interface RgbColor { red: number; green: number; blue: number }

function flattenGroups(items: GroupCard[]): GroupCard[] {
  return items.flatMap(group => [group, ...flattenGroups(group.groups ?? [])])
}
function groupCards(group: GroupCard): CreationCard[] {
  return [...group.children, ...group.groups.flatMap(groupCards)]
}
const activeGroup = computed(() => groupStack.value[groupStack.value.length - 1])
const steps = computed(() => activeGroup.value?.children ?? rootSteps.value)
const boardItems = computed<CanvasItem[]>(() => activeGroup.value
  ? [...activeGroup.value.children, ...activeGroup.value.groups, ...activeGroup.value.inputNodes, ...activeGroup.value.outputNodes]
  : [...rootSteps.value, ...groups.value, ...annotations.value])
const renderedBoardItems = computed<CanvasItem[]>(() => renderedLayerId.value === activeLayerId.value
  ? boardItems.value
  : [...renderedLayer.value.rootSteps, ...renderedLayer.value.groups, ...renderedLayer.value.annotations])
const backgroundLayers = computed(() => activeGroup.value ? [] : layers.value.slice(0, layers.value.findIndex(layer => layer.id === activeLayerId.value)).filter(layer => layer.visible))
const visibleCanvasLayers = computed(() => [...backgroundLayers.value, currentLayer.value])
const allCreationCards = computed(() => layers.value.flatMap(layer => [...layer.rootSteps, ...layer.groups.flatMap(groupCards)]))
const allGroups = computed(() => layers.value.flatMap(layer => flattenGroups(layer.groups)))
const activeStep = computed<CreationCard>(() => steps.value.find(step => step.id === activeStepId.value) ?? steps.value[0] ?? { kind: 'creation', id: -1, title: '新建创作', x: 100, y: 170, activeVersionId: '', batches: [], draft: currentLayer.value.draft })
const selectedGroup = computed(() => allGroups.value.find(group => group.id === focusedGroupId.value))
const selectedGroupOutput = computed(() => selectedGroup.value?.outputs.find(output => output.id === selectedGroup.value?.defaultOutputId) ?? selectedGroup.value?.outputs[0])
const selectedCreationCount = computed(() => selectedItemIds.value.filter(id => steps.value.some(step => step.id === id)).length)
const connectionCount = computed(() => allCreationCards.value.filter(step => Boolean(step.source)).length)
const draft = computed(() => activeStep.value.draft)
const selectedModel = computed(() => MODEL_CAPABILITIES.find(model => model.id === draft.value.modelId) ?? MODEL_CAPABILITIES[0])
const modelOptions = computed(() => MODEL_CAPABILITIES.filter(model => model.modes.includes(draft.value.mode)))
const activeInputLimit = computed(() => selectedModel.value.inputLimit)
const isOverModelLimit = computed(() => draft.value.references.length > activeInputLimit.value)
const invalidReferenceIds = computed(() => new Set(draft.value.references.slice(activeInputLimit.value).map(reference => reference.id)))
const generationBlocked = computed(() => currentLayer.value.locked || !draft.value.prompt.trim() || isOverModelLimit.value || Boolean(pendingDecision.value))
const visibleAssets = computed(() => assets.filter(asset => (assetFilter.value === 'all' || asset.type === assetFilter.value) && asset.title.includes(assetSearch.value.trim())))
const assetCounts = computed(() => ({ image: assets.filter(asset => asset.type === 'image').length, video: assets.filter(asset => asset.type === 'video').length }))
const projectCollections = computed(() => allGroups.value.map(group => ({
  group,
  kind: group.inputNodes.length || group.incomingSources.length ? 'process-set' as const : 'reference-set' as const,
})))
const collectionCounts = computed(() => ({
  reference: projectCollections.value.filter(item => item.kind === 'reference-set').length,
  process: projectCollections.value.filter(item => item.kind === 'process-set').length,
  personal: projectCollections.value.filter(item => item.group.sharing === 'personal').length,
  team: projectCollections.value.filter(item => item.group.sharing === 'team').length,
}))
const collectionMode = computed(() => ['reference-set', 'process-set', 'personal', 'team'].includes(assetFilter.value))
const visibleCollections = computed(() => projectCollections.value.filter(item => {
  const filterMatches = assetFilter.value === item.kind || assetFilter.value === item.group.sharing
  return filterMatches && item.group.title.includes(assetSearch.value.trim())
}))
const selectedCollection = computed(() => visibleCollections.value.find(item => item.group.id === selectedCollectionId.value) ?? visibleCollections.value[0])
const availableGroupOutputs = computed(() => allGroups.value.flatMap(group => group.id === activeGroupId.value ? [] : group.outputs.map(output => ({ group, output, version: groupOutputVersion(group, output) }))).filter(item => item.version))
const referenceSteps = computed(() => visibleCanvasLayers.value.flatMap(layer => [...layer.rootSteps, ...layer.groups.flatMap(groupCards)].map(step => ({ layer, step }))).filter(item => activeVersion(item.step)?.status === 'done'))
const colorFlow = computed(() => {
  const cardColors = new Map<number, RgbColor>()
  const groupColors = new Map<number, RgbColor>()
  const cardsById = new Map(allCreationCards.value.map(card => [card.id, card]))
  const groupsById = new Map(allGroups.value.map(group => [group.id, group]))
  const visitingCards = new Set<number>()
  const visitingGroups = new Set<number>()

  const sourceColor = (source: SourceRef): RgbColor => {
    if (source.kind === 'card') return cardColor(cardsById.get(source.cardId))
    return groupColor(groupsById.get(source.groupId))
  }
  const cardColor = (card?: CreationCard): RgbColor => {
    if (!card) return NEUTRAL_LINE_COLOR
    const cached = cardColors.get(card.id)
    if (cached) return cached
    if (visitingCards.has(card.id)) return NEUTRAL_LINE_COLOR
    visitingCards.add(card.id)
    const incoming = card.source ? sourceColor(card.source) : undefined
    const own = mediaColor(activeVersion(card))
    const color = !incoming ? own ?? NEUTRAL_LINE_COLOR : !own ? incoming : blendColors([[incoming, 1 - COLOR_DRIFT], [own, COLOR_DRIFT]])
    visitingCards.delete(card.id)
    cardColors.set(card.id, color)
    return color
  }
  const groupColor = (group?: GroupCard): RgbColor => {
    if (!group) return NEUTRAL_LINE_COLOR
    const cached = groupColors.get(group.id)
    if (cached) return cached
    if (visitingGroups.has(group.id)) return NEUTRAL_LINE_COLOR
    visitingGroups.add(group.id)
    const primaryOutput = group.outputs.find(output => output.id === group.defaultOutputId) ?? group.outputs[0]
    const primaryCard = primaryOutput ? group.children.find(card => card.id === primaryOutput.cardIds[0]) : undefined
    const primary = primaryCard ? cardColor(primaryCard) : undefined
    const primarySource = primaryCard?.source ? sourceKey(primaryCard.source) : undefined
    const incoming = group.incomingSources.filter(source => sourceKey(source) !== primarySource).map(sourceColor)
    const color = primary
      ? incoming.length ? blendColors([[primary, MAINLINE_WEIGHT], ...incoming.map(item => [item, (1 - MAINLINE_WEIGHT) / incoming.length] as [RgbColor, number])]) : primary
      : incoming.length ? blendColors(incoming.map(item => [item, 1 / incoming.length] as [RgbColor, number])) : NEUTRAL_LINE_COLOR
    visitingGroups.delete(group.id)
    groupColors.set(group.id, color)
    return color
  }

  allCreationCards.value.forEach(cardColor)
  allGroups.value.forEach(groupColor)
  return { cards: cardColors, groups: groupColors }
})
const trajectoryLinks = computed(() => {
  const linkLayer = (layer: BoardLayer, items: BoardItem[]) => items.flatMap(target => {
    const refs = target.kind === 'group' ? target.incomingSources : target.source ? [target.source] : []
    return refs.flatMap(sourceRef => {
      const source = resolveVisibleSource(sourceRef, layer, items)
      return source ? [{ ...createBezierTrajectoryLink(source, target, sourceRef), layerId: layer.id, background: layer.id !== activeLayerId.value }] : []
    })
  })
  if (activeGroup.value && renderedLayerId.value === activeLayerId.value) return linkLayer(currentLayer.value, activeGroup.value.children)
  return linkLayer(renderedLayer.value, [...renderedLayer.value.rootSteps, ...renderedLayer.value.groups])
})
const layerCacheViews = computed(() => {
  const activeIndex = layers.value.findIndex(layer => layer.id === activeLayerId.value)
  const cached = layers.value.filter((layer, index) => layer.id === handoffLayerId.value || Math.abs(index - activeIndex) <= 2).map(layer => {
    const layerIndex = layers.value.findIndex(item => item.id === layer.id)
    const rawDepth = activeIndex - layerIndex
    const active = layer.id === activeLayerId.value
    const outgoing = layer.id === handoffLayerId.value
    const items: BoardItem[] = [...layer.rootSteps, ...layer.groups]
    const links = items.flatMap(target => {
      const refs = target.kind === 'group' ? target.incomingSources : target.source ? [target.source] : []
      return refs.flatMap(sourceRef => {
        const source = resolveVisibleSource(sourceRef, layer, items)
        return source ? [createBezierTrajectoryLink(source, target, sourceRef)] : []
      })
    })
    const depth = active || outgoing ? 0 : Math.min(4, Math.max(1, rawDepth))
    const renderLevel = active || outgoing || depth === 1 ? 'full' : depth === 2 ? 'no-text' : 'silhouette'
    return { layer, links, depth, qualityDepth: Math.min(4, Math.max(1, Math.abs(rawDepth))), active, outgoing, visible: (rawDepth > 0 && layer.visible) || (outgoing && !handoffFading.value), transitioning: outgoing, renderLevel, viewport: outgoing ? handoffViewport.value : boardViewport.value }
  })
  const count = Math.max(1, cached.length)
  const padding = Math.max(canvasSize.value.width, canvasSize.value.height) * .2
  const area = Math.max(1, (canvasSize.value.width + padding * 2) * (canvasSize.value.height + padding * 2))
  const sharedDpr = Math.min(.65, window.devicePixelRatio || 1, Math.sqrt(2_000_000 / (area * count)))
  const depthQuality = [1, .52, .42, .32, .25]
  return cached.map(item => ({ ...item, dpr: item.active || item.outgoing ? .3 : Math.max(.25, sharedDpr * depthQuality[item.qualityDepth]), revision: layerRenderRevision(item.layer, item.links) }))
})
const incomingLayerScale = 1
const outgoingLayerScale = 1
const flowNodes = computed<Node[]>(() => renderedBoardItems.value.map(item => ({
  id: String(item.id),
  type: item.kind === 'group' ? 'group' : item.kind === 'input' ? 'group-input' : item.kind === 'output' ? 'group-output' : item.kind === 'text' ? 'text-annotation' : item.kind === 'brush' ? 'brush-annotation' : 'thought',
  position: { x: item.x, y: item.y },
  width: item.kind === 'text' ? 210 : item.kind === 'brush' ? item.width : item.kind === 'input' || item.kind === 'output' ? 190 : STEP_WIDTH,
  height: item.kind === 'text' ? 76 : item.kind === 'brush' ? item.height : item.kind === 'input' || item.kind === 'output' ? 72 : STEP_HEIGHT,
  draggable: !currentLayer.value.locked,
  selectable: !currentLayer.value.locked,
  selected: selectedItemIds.value.includes(item.id),
  connectable: false,
  focusable: false,
  deletable: false,
  data: item.kind === 'group'
    ? { group: item, outputs: groupOutputVersions(item), background: false }
    : item.kind === 'creation'
      ? { step: item, version: activeVersion(item), background: false }
      : item.kind === 'input'
        ? { port: item, background: false }
        : item.kind === 'output'
          ? { port: item, output: activeGroup.value?.outputs.find(output => output.id === item.outputId), background: false }
      : { note: item, background: false },
})))
const flowEdges = computed<Edge[]>(() => trajectoryLinks.value.map(link => ({
  id: `trail-${link.id}`,
  source: String(link.sourceId),
  target: String(link.targetId),
  sourceHandle: 'right',
  targetHandle: 'left',
  type: 'thought',
  selectable: false,
  focusable: false,
  deletable: false,
  data: link,
})))
const scale = computed(() => flow.getViewport().zoom)
const historyStep = computed(() => steps.value.find(step => step.id === historyStepId.value))
const allActiveVersions = computed(() => steps.value.map(activeVersion).filter((version): version is MediaVersion => Boolean(version)))
const viewerItem = computed<MediaViewerItem | null>(() => previewVersion.value ? {
  id: previewVersion.value.id,
  src: previewVersion.value.src,
  type: previewVersion.value.type,
  title: previewVersion.value.title,
  subtitle: '制作板版本',
} : null)

watch(() => draft.value.mode, () => {
  if (!modelOptions.value.some(model => model.id === draft.value.modelId)) draft.value.modelId = modelOptions.value[0].id
})

function versionsFor(step: CreationCard) { return step.batches.flatMap(batch => batch.versions) }
function historyCount(step: CreationCard) { return versionsFor(step).length }
function activeVersion(step: CreationCard) { return versionsFor(step).find(version => version.id === step.activeVersionId) }
function layerRenderRevision(layer: BoardLayer, links: ReturnType<typeof createBezierTrajectoryLink>[]) {
  const cards = [...layer.rootSteps, ...layer.groups.flatMap(group => group.children)]
  return JSON.stringify({
    cards: cards.map(card => { const version = activeVersion(card); return [card.id, card.x, card.y, card.activeVersionId, version?.src, version?.status] }),
    groups: layer.groups.map(group => [group.id, group.x, group.y, group.defaultOutputId, group.title]),
    annotations: layer.annotations,
    links: links.map(link => [link.id, link.p0, link.p1, link.p2, link.sourceColor, link.targetColor]),
  })
}
function blendColors(colors: Array<[RgbColor, number]>): RgbColor {
  const total = colors.reduce((sum, [, weight]) => sum + weight, 0) || 1
  return colors.reduce((result, [color, weight]) => ({
    red: result.red + color.red * weight / total,
    green: result.green + color.green * weight / total,
    blue: result.blue + color.blue * weight / total,
  }), { red: 0, green: 0, blue: 0 })
}
function colorHex(color: RgbColor) {
  return `#${[color.red, color.green, color.blue].map(channel => Math.round(channel).toString(16).padStart(2, '0')).join('')}`
}
function requestImageColor(version: MediaVersion) {
  const cached = sourceColorRequests.get(version.src)
  if (cached) return cached
  const request = new Promise<RgbColor | undefined>(resolve => {
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => {
      const scale = Math.min(1, 256 / Math.max(image.naturalWidth, image.naturalHeight))
      const width = Math.max(1, Math.round(image.naturalWidth * scale))
      const height = Math.max(1, Math.round(image.naturalHeight * scale))
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d', { willReadFrequently: true })
      try {
        if (!context) throw new Error('Canvas unavailable')
        context.drawImage(image, 0, 0, width, height)
        const main = getDominantColors(analyzeImageColors(context.getImageData(0, 0, width, height)), 1)[0]
        resolve(main ? { red: main.rgb >> 16, green: (main.rgb >> 8) & 255, blue: main.rgb & 255 } : undefined)
      } catch { resolve(undefined) }
    }
    image.onerror = () => resolve(undefined)
    image.src = version.src
  })
  sourceColorRequests.set(version.src, request)
  return request
}
function fallbackMediaColor(source: string): RgbColor {
  let hash = 0
  for (let index = 0; index < source.length; index++) hash = (hash * 31 + source.charCodeAt(index)) | 0
  return {
    red: 90 + (hash >>> 16 & 95),
    green: 90 + (hash >>> 8 & 95),
    blue: 90 + (hash & 95),
  }
}
function mediaColor(version?: MediaVersion) {
  if (!version) return undefined
  const cached = sourceColors.value[version.src]
  if (cached) return cached
  if (version.type === 'image') void requestImageColor(version).then(color => {
    if (color && !sourceColors.value[version.src]) sourceColors.value = { ...sourceColors.value, [version.src]: color }
  })
  return fallbackMediaColor(version.src)
}
function groupOutputVersion(group: GroupCard, output: GroupOutput) {
  const card = group.children.find(child => child.id === output.cardIds[0])
  return card ? activeVersion(card) : undefined
}
function groupOutputVersionsList(group: GroupCard, output: GroupOutput) {
  return output.cardIds.map(cardId => group.children.find(child => child.id === cardId)).map(activeVersion).filter((version): version is MediaVersion => Boolean(version))
}
function groupOutputVersions(group: GroupCard) {
  return group.outputs.map(output => ({ output, version: groupOutputVersion(group, output) })).filter(item => item.version)
}
function defaultGroupVersion(group: GroupCard) {
  const output = group.outputs.find(item => item.id === group.defaultOutputId) ?? group.outputs[0]
  return output ? groupOutputVersion(group, output) : undefined
}
function sourceKey(source: SourceRef) {
  return source.kind === 'card' ? `card-${source.cardId}` : `group-${source.groupId}-${source.outputId}`
}
function resolveVisibleSource(source: SourceRef, layer = currentLayer.value, items: BoardItem[] = boardItems.value): BoardItem | undefined {
  const sourceLayer = source.layerId ? layers.value.find(item => item.id === source.layerId) ?? layer : layer
  if (sourceLayer.id !== layer.id) return undefined
  if (source.kind === 'card') return items.find((item): item is CreationCard => item.kind === 'creation' && item.id === source.cardId)
  return activeGroup.value ? undefined : sourceLayer.groups.find(group => group.id === source.groupId)
}
function createBezierTrajectoryLink(source: BoardItem, target: BoardItem, sourceRef?: SourceRef) {
  const sourceColor = source.kind === 'group' ? colorFlow.value.groups.get(source.id) ?? NEUTRAL_LINE_COLOR : colorFlow.value.cards.get(source.id) ?? NEUTRAL_LINE_COLOR
  const targetColor = target.kind === 'group' ? colorFlow.value.groups.get(target.id) ?? NEUTRAL_LINE_COLOR : colorFlow.value.cards.get(target.id) ?? NEUTRAL_LINE_COLOR
  const sourceCenter = { x: source.x + STEP_WIDTH / 2, y: source.y + STEP_HEIGHT / 2 }
  const targetCenter = { x: target.x + STEP_WIDTH / 2, y: target.y + STEP_HEIGHT / 2 }
  const dx = targetCenter.x - sourceCenter.x
  const dy = targetCenter.y - sourceCenter.y
  const distance = Math.max(1, Math.hypot(dx, dy))
  const direction = { x: dx / distance, y: dy / distance }
  const sourceRadius = Math.min(STEP_WIDTH / 2 / Math.max(.001, Math.abs(direction.x)), STEP_HEIGHT / 2 / Math.max(.001, Math.abs(direction.y)))
  const targetRadius = sourceRadius
  const clearance = distance - sourceRadius - targetRadius
  const portGap = Math.max(0, Math.min(TRAIL_PORT_GAP, clearance * .2))
  const sourceReach = clearance > 0 ? sourceRadius + portGap : distance / 2
  const targetReach = clearance > 0 ? targetRadius + portGap : distance / 2
  const p0 = { x: sourceCenter.x + direction.x * sourceReach, y: sourceCenter.y + direction.y * sourceReach }
  const p2 = { x: targetCenter.x - direction.x * targetReach, y: targetCenter.y - direction.y * targetReach }
  const heightDelta = p2.y - p0.y
  const heightBend = Math.max(-72, Math.min(72, heightDelta * .28))
  const p1 = { x: (p0.x + p2.x) / 2, y: (p0.y + p2.y) / 2 + heightBend }
  const endDirectionLength = Math.max(1, Math.hypot(p2.x - p1.x, p2.y - p1.y))
  const endDirection = { x: (p2.x - p1.x) / endDirectionLength, y: (p2.y - p1.y) / endDirectionLength }
  const arrowBase = { x: p2.x - endDirection.x * 7, y: p2.y - endDirection.y * 7 }
  const arrowNormal = { x: -endDirection.y * 3.2, y: endDirection.x * 3.2 }
  const length = Math.hypot(p2.x - p0.x, p2.y - p0.y)
  const fade = Math.min(1, Math.max(0, (length - TRAIL_FADE_LENGTH) / TRAIL_FADE_LENGTH))
  const visibility = Math.min(1, Math.max(0, clearance / 20))
  return {
    id: `${source.id}-${target.id}-${sourceRef ? sourceKey(sourceRef) : 'direct'}`,
    sourceId: source.id,
    targetId: target.id,
    p0,
    p1,
    p2,
    arrowPoints: `${p2.x},${p2.y} ${arrowBase.x + arrowNormal.x},${arrowBase.y + arrowNormal.y} ${arrowBase.x - arrowNormal.x},${arrowBase.y - arrowNormal.y}`,
    sourceColor: colorHex(sourceColor),
    targetColor: colorHex(targetColor),
    shoulderOpacity: .7 * (1 - fade * .45) * visibility,
    centerOpacity: .9 * (1 - fade * .2) * visibility,
    d: `M ${p0.x} ${p0.y} Q ${p1.x} ${p1.y}, ${p2.x} ${p2.y}`,
  }
}
function cloneDraft(source: CreationDraft, adopted: MediaVersion): CreationDraft {
  const adoptedReference: ReferenceInput = { id: `canvas-${adopted.id}`, source: 'canvas', type: adopted.type, title: adopted.title, src: adopted.src }
  const references = [adoptedReference, ...source.references.map(reference => ({ ...reference }))]
  return { ...source, mode: adopted.type, references: [...new Map(references.map(reference => [reference.id, reference])).values()] }
}
function canAddConnection() {
  if (connectionCount.value < MAX_CONNECTIONS) return true
  groupMessage.value = `连接线已达到 ${MAX_CONNECTIONS} 条上限`
  return false
}
function newCardFrom(source: CreationCard, version: MediaVersion, batch: GenerationBatch) {
  if (!canAddConnection()) return
  const siblingCount = steps.value.filter(step => step.source?.kind === 'card' && step.source.cardId === source.id).length
  const step: CreationCard = {
    kind: 'creation',
    id: Date.now(),
    source: { kind: 'card', cardId: source.id, layerId: activeLayerId.value },
    title: version.type === 'image' ? '图片探索' : '视频探索',
    x: source.x + STEP_GAP,
    y: source.y + siblingCount * (STEP_HEIGHT + 36),
    activeVersionId: version.id,
    batches: [batch],
    draft: cloneDraft(source.draft, version),
  }
  steps.value.push(step)
  activeStepId.value = step.id
  focusedStepId.value = step.id
  nextTick(resetView)
}
function createGeneratingCard(source: CreationCard, batch: GenerationBatch) {
  const pendingVersion = batch.versions[0]
  const siblingCount = steps.value.filter(step => step.source?.kind === 'card' && step.source.cardId === source.id).length
  const sourceVersion = activeVersion(source) ?? pendingVersion
  const step: CreationCard = {
    kind: 'creation',
    id: nextItemId(),
    source: { kind: 'card', cardId: source.id, layerId: activeLayerId.value },
    title: pendingVersion.type === 'image' ? '图片生成中' : '视频生成中',
    x: source.x + STEP_GAP,
    y: source.y + siblingCount * (STEP_HEIGHT + 36),
    activeVersionId: pendingVersion.id,
    batches: [batch],
    draft: cloneDraft(source.draft, sourceVersion),
  }
  steps.value.push(step)
  activeStepId.value = step.id
  focusedStepId.value = step.id
  nextTick(resetView)
  return step
}
function createGeneratingRoot(batch: GenerationBatch) {
  const pendingVersion = batch.versions[0]
  const step: CreationCard = {
    kind: 'creation',
    id: nextItemId(),
    title: pendingVersion.type === 'image' ? '图片生成中' : '视频生成中',
    x: 100,
    y: 170,
    activeVersionId: pendingVersion.id,
    batches: [batch],
    draft: { ...currentLayer.value.draft, references: currentLayer.value.draft.references.map(reference => ({ ...reference })) },
  }
  steps.value.push(step)
  activeStepId.value = step.id
  focusedStepId.value = step.id
  nextTick(resetView)
  return step
}
function handlePaneClick() {
  if (!activeGroup.value && !rootSteps.value.length && groups.value.length) {
    focusedGroupId.value = groups.value[0].id
    selectedItemIds.value = [groups.value[0].id]
    return
  }
  focusedStepId.value = null
  focusedGroupId.value = null
  selectedItemIds.value = []
  advancedOpen.value = false
  referencePickerOpen.value = false
  mobileAssetsOpen.value = false
}
function handleNodeClick({ node }: NodeMouseEvent) {
  const item = boardItems.value.find(candidate => String(candidate.id) === node.id)
  if (!item) return
  selectBoardItem(item)
}
function selectBoardItem(item: CanvasItem, event?: MouseEvent) {
  const multi = Boolean(event?.shiftKey || event?.ctrlKey || event?.metaKey)
  if (multi) {
    const selected = new Set(selectedItemIds.value)
    if (selected.has(item.id)) selected.delete(item.id)
    else selected.add(item.id)
    selectedItemIds.value = [...selected]
  } else selectedItemIds.value = [item.id]
  groupMessage.value = ''
  if (item.kind === 'group') {
    focusedGroupId.value = item.id
    focusedStepId.value = null
  } else if (item.kind === 'creation') {
    activeStepId.value = item.id
    focusedStepId.value = item.id
    focusedGroupId.value = null
  } else {
    focusedStepId.value = null
    focusedGroupId.value = null
  }
}
function syncStepPosition({ node, nodes }: NodeDragEvent) {
  const movedNodes = nodes.length ? nodes : [node]
  movedNodes.forEach(moved => {
    const item = boardItems.value.find(candidate => String(candidate.id) === moved.id)
    if (!item) return
    item.x = moved.position.x
    item.y = moved.position.y
  })
}
function handleNodeDragStop(event: NodeDragEvent) {
  syncStepPosition(event)
  setCanvasMoving(false)
}
function handleNodesChange(changes: NodeChange[]) {
  const selected = new Set(selectedItemIds.value)
  changes.forEach(change => {
    if (change.type !== 'select') return
    if (change.selected) selected.add(Number(change.id))
    else selected.delete(Number(change.id))
  })
  selectedItemIds.value = [...selected]
}
function prepareCanvasSelection(event: PointerEvent) {
  if (event.button !== 0 || !(event.target as Element).classList.contains('vue-flow__pane')) return
  if (canvasTool.value === 'brush') {
    event.preventDefault()
    brushPoints = [flow.screenToFlowCoordinate({ x: event.clientX, y: event.clientY })]
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
    return
  }
  additiveCanvasSelection = event.shiftKey
  selectionBaseIds = event.shiftKey ? [...selectedItemIds.value] : []
}
function extendBrush(event: PointerEvent) {
  if (!brushPoints.length) return
  const point = flow.screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  const previous = brushPoints[brushPoints.length - 1]
  if (Math.hypot(point.x - previous.x, point.y - previous.y) >= 2) brushPoints.push(point)
}
function finishBrush(event: PointerEvent) {
  if (!brushPoints.length) return
  ;(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId)
  if (brushPoints.length > 1) {
    const minX = Math.min(...brushPoints.map(point => point.x))
    const minY = Math.min(...brushPoints.map(point => point.y))
    const maxX = Math.max(...brushPoints.map(point => point.x))
    const maxY = Math.max(...brushPoints.map(point => point.y))
    const padding = 12
    const path = brushPoints.map((point, index) => `${index ? 'L' : 'M'} ${point.x - minX + padding} ${point.y - minY + padding}`).join(' ')
    const note: BrushAnnotation = { kind: 'brush', id: nextItemId(), x: minX - padding, y: minY - padding, width: Math.max(32, maxX - minX + padding * 2), height: Math.max(32, maxY - minY + padding * 2), path }
    annotations.value.push(note)
    selectedItemIds.value = [note.id]
  }
  brushPoints = []
}
function finishCanvasSelection() {
  if (additiveCanvasSelection) selectedItemIds.value = [...new Set([...selectionBaseIds, ...selectedItemIds.value])]
  selectionBaseIds = []
  additiveCanvasSelection = false
}
function nextItemId() {
  return Math.max(0, ...allCreationCards.value.map(item => item.id), ...allGroups.value.map(item => item.id), ...layers.value.flatMap(layer => layer.annotations).map(item => item.id)) + 1
}
function packSelectedCards() {
  if (activeGroup.value && groupStack.value.length >= 4) {
    groupMessage.value = '最多可嵌套 4 层子画板'
    return
  }
  const selectedIds = new Set(selectedItemIds.value)
  const containerSteps = activeGroup.value?.children ?? rootSteps.value
  const containerGroups = activeGroup.value?.groups ?? groups.value
  const children = containerSteps.filter(step => selectedIds.has(step.id))
  if (children.length < 2) return
  const childIds = new Set(children.map(child => child.id))
  const minX = Math.min(...children.map(child => child.x))
  const minY = Math.min(...children.map(child => child.y))
  const groupId = nextItemId()
  const outputs: GroupOutput[] = []
  const outputByCard = new Map<number, GroupOutput>()
  const boundaryLinks: GroupBoundaryLink[] = []
  const incomingSources: SourceRef[] = []
  children.forEach(child => {
    if (!child.source || (child.source.kind === 'card' && childIds.has(child.source.cardId))) return
    boundaryLinks.push({ direction: 'incoming', targetCardId: child.id, source: { ...child.source } })
    if (!incomingSources.some(source => sourceKey(source) === sourceKey(child.source!))) incomingSources.push({ ...child.source })
  })
  containerSteps.forEach(target => {
    if (childIds.has(target.id) || target.source?.kind !== 'card' || !childIds.has(target.source.cardId)) return
    const originalSource = { ...target.source }
    boundaryLinks.push({ direction: 'outgoing', targetCardId: target.id, source: originalSource })
    const output = outputByCard.get(target.source.cardId)
    if (output) target.source = { kind: 'group-output', groupId, outputId: output.id }
  })
  children.forEach(child => {
    child.x -= minX
    child.y -= minY
  })
  const group: GroupCard = {
    kind: 'group',
    id: groupId,
    title: `子面板 ${String(++groupCount).padStart(2, '0')}`,
    x: minX,
    y: minY,
    children,
    groups: [],
    inputNodes: [],
    outputNodes: [],
    outputs,
    defaultOutputId: outputs[0]?.id,
    incomingSources,
    viewport: { x: 0, y: 0, zoom: 1 },
    viewportReady: false,
    boundaryLinks,
    sharing: 'personal',
  }
  if (activeGroup.value) activeGroup.value.children = containerSteps.filter(step => !childIds.has(step.id))
  else rootSteps.value = containerSteps.filter(step => !childIds.has(step.id))
  containerGroups.push(group)
  selectedItemIds.value = [group.id]
  focusedStepId.value = null
  focusedGroupId.value = group.id
}
async function enterGroup(group: GroupCard) {
  if (groupStack.value.length >= 4) {
    groupMessage.value = '最多可嵌套 4 层子画板'
    return
  }
  if (activeGroup.value) {
    activeGroup.value.viewport = flow.getViewport()
    activeGroup.value.viewportReady = true
  } else rootViewport.value = flow.getViewport()
  groupStack.value.push(group)
  activeGroupId.value = group.id
  focusedGroupId.value = null
  selectedItemIds.value = []
  const firstChild = group.children[0]
  if (firstChild) {
    activeStepId.value = firstChild.id
    focusedStepId.value = firstChild.id
  }
  await nextTick()
  if (group.viewportReady) await flow.setViewport(group.viewport, { duration: 180 })
  else {
    await resetView()
    group.viewport = flow.getViewport()
    group.viewportReady = true
  }
}
async function leaveGroup() {
  const group = activeGroup.value
  if (!group) return
  group.viewport = flow.getViewport()
  group.viewportReady = true
  groupStack.value.pop()
  activeGroupId.value = activeGroup.value?.id ?? null
  focusedStepId.value = null
  selectedItemIds.value = []
  await nextTick()
  await flow.setViewport(activeGroup.value?.viewport ?? rootViewport.value, { duration: 180 })
}
async function leaveToGroup(index: number) {
  while (groupStack.value.length - 1 > index) await leaveGroup()
}
function outputInUse(group: GroupCard, output: GroupOutput) {
  return rootSteps.value.some(step => step.source?.kind === 'group-output' && step.source.groupId === group.id && step.source.outputId === output.id)
}
function toggleGroupOutput(step: CreationCard) {
  const group = activeGroup.value
  if (!group) return
  groupMessage.value = ''
  const existing = group.outputs.find(output => output.cardIds.includes(step.id))
  if (existing) {
    if (outputInUse(group, existing)) {
      groupMessage.value = '该输出正在被外部创作使用，请先重新指定来源'
      return
    }
    existing.cardIds = existing.cardIds.filter(cardId => cardId !== step.id)
    if (!existing.cardIds.length) {
      group.outputs = group.outputs.filter(output => output.id !== existing.id)
      group.outputNodes = group.outputNodes.filter(node => node.outputId !== existing.id)
    }
    if (group.defaultOutputId === existing.id) group.defaultOutputId = group.outputs[0]?.id
    return
  }
  const output = group.outputs.find(item => item.id === group.defaultOutputId) ?? group.outputs[0] ?? createGroupOutput(group)
  output.cardIds.push(step.id)
  group.defaultOutputId ||= output.id
}
function createGroupOutput(group: GroupCard) {
  const output: GroupOutput = { id: crypto.randomUUID(), name: `输出 ${group.outputs.length + 1}`, cardIds: [] }
  group.outputs.push(output)
  group.outputNodes.push({ kind: 'output', id: nextItemId(), x: 520, y: 80 + group.outputNodes.length * 96, outputId: output.id })
  group.defaultOutputId ||= output.id
  return output
}
function addGroupInputNode() {
  const group = activeGroup.value
  if (!group) return
  group.inputNodes.push({ kind: 'input', id: nextItemId(), x: 50, y: 80 + group.inputNodes.length * 96, name: `输入 ${group.inputNodes.length + 1}` })
}
function addGroupOutputNode() {
  const group = activeGroup.value
  if (!group) return
  createGroupOutput(group)
}
function groupInputVersions(group: GroupCard) {
  return group.incomingSources.flatMap(source => {
    if (source.kind === 'card') return allCreationCards.value.filter(card => card.id === source.cardId).map(activeVersion).filter((version): version is MediaVersion => Boolean(version))
    const sourceGroup = allGroups.value.find(candidate => candidate.id === source.groupId)
    const output = sourceGroup?.outputs.find(candidate => candidate.id === source.outputId)
    return sourceGroup && output ? groupOutputVersionsList(sourceGroup, output) : []
  })
}
function addGroupInputReferences() {
  const group = activeGroup.value
  if (!group) return
  groupInputVersions(group).forEach((version, index) => addReference({ source: 'group', type: version.type, title: `${group.title} 输入 ${index + 1}`, src: version.src }, `group-input-${group.id}-${index}`))
}
function addActiveStepToGroupInput(group: GroupCard) {
  const step = activeStep.value
  if (step.id < 0 || groupCards(group).some(child => child.id === step.id)) return
  const source: SourceRef = { kind: 'card', cardId: step.id, layerId: activeLayerId.value }
  if (!group.incomingSources.some(item => sourceKey(item) === sourceKey(source))) group.incomingSources.push(source)
}
function isGroupOutput(step: CreationCard) {
  return Boolean(activeGroup.value?.outputs.some(output => output.cardIds.includes(step.id)))
}
function setDefaultOutput(group: GroupCard, output: GroupOutput) {
  group.defaultOutputId = output.id
  groupMessage.value = ''
}
function moveGroupOutput(group: GroupCard, output: GroupOutput, change: number) {
  const index = group.outputs.findIndex(item => item.id === output.id)
  const nextIndex = index + change
  if (index < 0 || nextIndex < 0 || nextIndex >= group.outputs.length) return
  const [item] = group.outputs.splice(index, 1)
  group.outputs.splice(nextIndex, 0, item)
}
function createFromGroupOutput(group: GroupCard, output: GroupOutput) {
  const sourceCard = group.children.find(child => child.id === output.cardIds[0])
  const sourceVersions = groupOutputVersionsList(group, output)
  const sourceVersion = sourceVersions[0]
  if (!sourceCard || !sourceVersion || activeGroup.value || !canAddConnection()) return
  const version = { ...sourceVersion, id: crypto.randomUUID(), title: output.name }
  const step: CreationCard = {
    kind: 'creation',
    id: nextItemId(),
    source: { kind: 'group-output', groupId: group.id, outputId: output.id, layerId: activeLayerId.value },
    title: output.name,
    x: group.x + STEP_GAP,
    y: group.y + rootSteps.value.filter(item => item.source?.kind === 'group-output' && item.source.groupId === group.id).length * (STEP_HEIGHT + 36),
    activeVersionId: version.id,
    batches: [initialBatch(version)],
    draft: cloneDraft(sourceCard.draft, version),
  }
  step.draft.references = sourceVersions.map((version, index) => ({ id: `group-${group.id}-${output.id}-${index}`, source: 'group', type: version.type, title: `${output.name} ${index + 1}`, src: version.src }))
  rootSteps.value.push(step)
  activeStepId.value = step.id
  focusedStepId.value = step.id
  focusedGroupId.value = null
  selectedItemIds.value = [step.id]
  nextTick(resetView)
}
function addGroupOutputReference(group: GroupCard, output: GroupOutput) {
  const versions = groupOutputVersionsList(group, output)
  const layer = layers.value.find(item => item.groups.some(candidate => candidate.id === group.id))
  versions.forEach((version, index) => addReference({ source: 'group', type: version.type, title: `${layer?.id === activeLayerId.value ? '' : `${layer?.name} · `}${group.title} · ${output.name} ${index + 1}`, src: version.src }, `group-${layer?.id ?? 'current'}-${group.id}-${output.id}-${index}`))
}
function dissolveGroup(group: GroupCard) {
  group.children.forEach(child => {
    child.x += group.x
    child.y += group.y
  })
  rootSteps.value.forEach(step => {
    if (step.source?.kind !== 'group-output' || step.source.groupId !== group.id) return
    const resolved = group.outputs.find(item => item.id === (step.source as Extract<SourceRef, { kind: 'group-output' }>).outputId)
    if (resolved?.cardIds[0]) step.source = { kind: 'card', cardId: resolved.cardIds[0] }
    else step.source = undefined
  })
  rootSteps.value.push(...group.children)
  groups.value = groups.value.filter(item => item.id !== group.id)
  focusedGroupId.value = null
  selectedItemIds.value = group.children.map(child => child.id)
  const firstChild = group.children[0]
  if (firstChild) {
    activeStepId.value = firstChild.id
    focusedStepId.value = firstChild.id
  }
  nextTick(resetView)
}
function zoomBy(delta: number) {
  const nextScale = Math.min(1.5, Math.max(.45, scale.value + delta))
  flow.zoomTo(nextScale, { duration: 120 })
}
const canAddLayer = computed(() => layers.value.length < 10)
function layerIsEmpty(layer: BoardLayer) {
  return !layer.rootSteps.length && !layer.groups.length && !layer.annotations.length
}
function startLayerPanelDrag(event: PointerEvent) {
  if ((event.target as HTMLElement).closest('button, input')) return
  closeLayerContextMenu()
  const panel = layerPanelElement.value
  if (!panel) return
  const rect = panel.getBoundingClientRect()
  layerPanelDrag = { offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top }
  layerPanelPosition.value = { left: rect.left, top: rect.top }
  window.addEventListener('pointermove', moveLayerPanel)
  window.addEventListener('pointerup', stopLayerPanelDrag, { once: true })
}
function moveLayerPanel(event: PointerEvent) {
  if (!layerPanelDrag || !layerPanelElement.value) return
  const rect = layerPanelElement.value.getBoundingClientRect()
  layerPanelPosition.value = {
    left: Math.max(8, Math.min(window.innerWidth - rect.width - 8, event.clientX - layerPanelDrag.offsetX)),
    top: Math.max(68, Math.min(window.innerHeight - rect.height - 8, event.clientY - layerPanelDrag.offsetY)),
  }
}
function stopLayerPanelDrag() {
  layerPanelDrag = null
  window.removeEventListener('pointermove', moveLayerPanel)
  window.removeEventListener('pointermove', moveAssetPanel)
}
const contextLayer = computed(() => layerContextMenu.value ? layers.value.find(layer => layer.id === layerContextMenu.value?.layerId) : undefined)
function openLayerContextMenu(event: MouseEvent, layer: BoardLayer) {
  event.preventDefault()
  event.stopPropagation()
  layerContextMenu.value = {
    layerId: layer.id,
    x: Math.min(event.clientX, window.innerWidth - 168),
    y: Math.min(event.clientY, window.innerHeight - 190),
  }
}
function closeLayerContextMenu() {
  layerContextMenu.value = null
}
async function beginLayerRename(layer: BoardLayer) {
  renamingLayerId.value = layer.id
  closeLayerContextMenu()
  await nextTick()
  const input = layerPanelElement.value?.querySelector<HTMLInputElement>('.layer-name-editor')
  input?.focus()
  input?.select()
}
function finishLayerRename(layer: BoardLayer) {
  layer.name = layer.name.trim() || '未命名图层'
  renamingLayerId.value = null
}
function handleLayerRowClick(event: MouseEvent, layer: BoardLayer) {
  if (renamingLayerId.value || (event.target as HTMLElement).closest('input, button')) return
  closeLayerContextMenu()
  void selectLayer(layer)
}
async function selectLayer(layer: BoardLayer, _saveCurrentViewport = true, _animateViewport = true) {
  if (layer.id === activeLayerId.value) return
  beginLayerHandoff(layer)
  layerSwitching.value = true
  activeLayerId.value = layer.id
  activeGroupId.value = null
  groupStack.value = []
  focusedGroupId.value = null
  selectedItemIds.value = []
  const first = layer.rootSteps[0]
  activeStepId.value = first?.id ?? 0
  focusedStepId.value = first?.id ?? null
  await nextTick()
  boardViewport.value = { ...flow.getViewport() }
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
  prepareHandoffMedia(layer)
  renderedLayerId.value = layer.id
  await nextTick()
  await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
  handoffReleaseArmed = true
  releaseLayerHandoffWhenReady()
}

function beginLayerHandoff(layer: BoardLayer) {
  window.clearTimeout(handoffTimer)
  window.clearTimeout(handoffFallbackTimer)
  const currentIndex = layers.value.findIndex(item => item.id === activeLayerId.value)
  const targetIndex = layers.value.findIndex(item => item.id === layer.id)
  transitionDirection.value = targetIndex >= currentIndex ? 'up' : 'down'
  handoffLayerId.value = activeLayerId.value
  handoffViewport.value = { ...flow.getViewport() }
  handoffFading.value = false
  handoffReleaseArmed = false
  handoffReleaseScheduled = false
  pendingHandoffMedia.clear()
}
function prepareHandoffMedia(layer: BoardLayer) {
  const viewport = flow.getViewport()
  const zoom = Math.max(.001, viewport.zoom)
  const bounds = { left: -viewport.x / zoom, top: -viewport.y / zoom, right: (-viewport.x + canvasSize.value.width) / zoom, bottom: (-viewport.y + canvasSize.value.height) / zoom }
  const visible = (item: BoardItem) => item.x + STEP_WIDTH >= bounds.left && item.y + STEP_HEIGHT >= bounds.top && item.x <= bounds.right && item.y <= bounds.bottom
  pendingHandoffMedia = new Set([
    ...layer.rootSteps.filter(visible).map(activeVersion),
    ...layer.groups.filter(visible).map(defaultGroupVersion),
  ].filter((version): version is MediaVersion => Boolean(version?.src)).map(version => version.id))
  handoffFallbackTimer = window.setTimeout(() => {
    pendingHandoffMedia.clear()
    releaseLayerHandoffWhenReady()
  }, 1200)
}
function markHandoffMediaReady(versionId?: string) {
  if (!versionId || !pendingHandoffMedia.delete(versionId)) return
  releaseLayerHandoffWhenReady()
}
function releaseLayerHandoffWhenReady() {
  if (!handoffReleaseArmed || pendingHandoffMedia.size || handoffReleaseScheduled || !handoffLayerId.value) return
  handoffReleaseScheduled = true
  const layerId = handoffLayerId.value
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (handoffLayerId.value !== layerId) return
    handoffFading.value = true
    handoffTimer = window.setTimeout(() => {
      if (handoffLayerId.value === layerId) handoffLayerId.value = null
      handoffFading.value = false
      handoffReleaseScheduled = false
      layerSwitching.value = false
    }, TRANSITION_MS)
  }))
}
function addLayer() {
  if (!canAddLayer.value) {
    groupMessage.value = '最多只能创建 10 个图层'
    return
  }
  const layer: BoardLayer = { id: crypto.randomUUID(), name: `画板 ${layers.value.length + 1}`, visible: true, locked: false, rootSteps: [], groups: [], annotations: [], draft: initialDraft('image', ''), viewport: flow.getViewport() }
  layers.value.push(layer)
  void selectLayer(layer, true, false)
}
async function removeLayer(layer: BoardLayer) {
  if (layers.value.length === 1 || !layerIsEmpty(layer)) return
  const index = layers.value.findIndex(item => item.id === layer.id)
  const nextLayer = layers.value[Math.max(0, index - 1)]
  const wasActive = activeLayerId.value === layer.id
  if (wasActive) await selectLayer(nextLayer, false, false)
  if (wasActive) await new Promise<void>(resolve => window.setTimeout(resolve, 520))
  layers.value.splice(index, 1)
}

function navigateFromMinimap(point: { x: number; y: number }) {
  void flow.setCenter(point.x, point.y, { zoom: boardViewport.value.zoom, duration: 140 })
}
function selectLayerFromMinimap(layerId: string) {
  const layer = layers.value.find(item => item.id === layerId)
  if (layer) void selectLayer(layer)
}
function setCanvasMoving(moving: boolean) {
  isCanvasMoving.value = moving
  if (!moving) {
    boardViewport.value = { ...flow.getViewport() }
    queueBoardSave()
  }
}
function updateBoardViewport(event: any) {
  const viewport = event?.flowTransform ?? event
  if (Number.isFinite(viewport?.x) && Number.isFinite(viewport?.y) && Number.isFinite(viewport?.zoom)) boardViewport.value = { x: viewport.x, y: viewport.y, zoom: viewport.zoom }
}
async function resetView() {
  await nextTick()
  await flow.fitView({
    padding: {
      top: '56px',
      right: assetsOpen.value && assetFixed.value ? '384px' : '60px',
      bottom: controlsOpen.value ? '292px' : '72px',
      left: '64px',
    },
    minZoom: .45,
    maxZoom: 1,
    duration: 220,
  })
  boardViewport.value = { ...flow.getViewport() }
}

function openPreview(version?: MediaVersion) { if (version) previewVersion.value = version }
function movePreview(change: number) {
  if (!previewVersion.value || !allActiveVersions.value.length) return
  const index = allActiveVersions.value.findIndex(version => version.id === previewVersion.value?.id)
  previewVersion.value = allActiveVersions.value[(index + change + allActiveVersions.value.length) % allActiveVersions.value.length]
}
function generationQuality() {
  return draft.value.quality === 'draft' ? 'low' : draft.value.quality === 'high' ? 'high' : 'medium'
}
function pendingVersions(mode: MediaType, count: number, prompt: string) {
  return Array.from({ length: count }, (_, index) => ({
    id: crypto.randomUUID(), type: mode, title: `${mode === 'image' ? '图片候选' : '视频候选'} ${index + 1}`,
    src: '', prompt, status: 'generating' as const,
  }))
}
function finishGeneration(batch: GenerationBatch, urls: string[]) {
  batch.versions = urls.map((src, index) => ({
    ...batch.versions[index],
    id: batch.versions[index]?.id ?? crypto.randomUUID(),
    title: `${batch.versions[index]?.type === 'video' ? '视频候选' : '图片候选'} ${index + 1}`,
    src,
    status: 'done' as const,
  }))
}
function failGeneration(batch: GenerationBatch, message: string) {
  batch.versions.forEach(version => { version.status = 'error'; version.error = message })
}
async function referenceFile(reference: ReferenceInput) {
  const response = await fetch(reference.src)
  if (!response.ok) throw new Error(`无法读取参考素材：${reference.title}`)
  const blob = await response.blob()
  const extension = reference.type === 'video' ? 'mp4' : blob.type.split('/')[1] || 'png'
  return new File([blob], `${reference.title}.${extension}`, { type: blob.type })
}
async function createGeneration() {
  if (generationBlocked.value) return
  const source = activeStep.value
  if (source.id !== -1 && !canAddConnection()) return
  const mode = draft.value.mode
  const batch: GenerationBatch = {
    id: crypto.randomUUID(),
    versions: pendingVersions(mode, draft.value.generationCount, draft.value.prompt),
  }
  const target = source.id === -1 ? createGeneratingRoot(batch) : createGeneratingCard(source, batch)
  pendingDecision.value = { sourceCardId: source.id, targetCardId: target.id, batch }
  try {
    const userId = getCurrentUserId() ?? undefined
    const models = await getApiModels(mode)
    const model = models[0]
    if (!model) throw new Error(`未配置可用的${mode === 'image' ? '图片' : '视频'}生成模型`)
    if (mode === 'image') {
      const inputs: InputImage[] = draft.value.references
        .filter(reference => reference.type === 'image')
        .map(reference => ({ file: null, preview: reference.src, assetLocation: '' }))
      const result = await submitImageGeneration({
        modelId: model.id,
        prompt: draft.value.prompt,
        aspect_ratio: draft.value.ratio,
        quality: generationQuality(),
        batchSize: draft.value.generationCount,
        img2img: inputs.length > 0,
        inputImages: inputs,
        userId,
      })
      const urls = result.taskId
        ? (await pollTaskUntilDone(result.taskId, userId, 'image')).images.map(item => item.url).filter((url): url is string => Boolean(url))
        : result.images ?? []
      if (!urls.length) throw new Error('生成任务没有返回图片')
      finishGeneration(batch, urls)
    } else {
      const references = [...draft.value.references]
      const result = references.length
        ? await submitImg2VideoGeneration({ modelId: model.id, prompt: draft.value.prompt, ratio: draft.value.ratio, resolution: '720p', duration: 5, inputFiles: await Promise.all(references.map(referenceFile)), inputAssetPreviews: [], userId })
        : await submitVideoGeneration({ modelId: model.id, prompt: draft.value.prompt, ratio: draft.value.ratio, resolution: '720p', duration: 5, userId })
      const urls = result.taskId
        ? (await pollTaskUntilDone(result.taskId, userId, 'video')).images.map(item => item.url).filter((url): url is string => Boolean(url))
        : result.videoUrl ? [result.videoUrl] : []
      if (!urls.length) throw new Error('生成任务没有返回视频')
      finishGeneration(batch, urls)
    }
    target.title = mode === 'image' ? '图片探索' : '视频探索'
  } catch (error: any) {
    failGeneration(batch, error?.message || '生成失败')
    target.title = '生成失败'
  }
}
function selectCandidate(version: MediaVersion) {
  if (version.status === 'done' && pendingDecision.value) pendingDecision.value.selectedVersionId = version.id
}
function closeDecision() {
  const decision = pendingDecision.value
  if (!decision) return
  pendingDecision.value = null
}
function adoptCandidate(continueToNext: boolean) {
  const decision = pendingDecision.value
  if (!decision?.selectedVersionId) return
  const target = steps.value.find(step => step.id === decision.targetCardId)
  const version = decision.batch.versions.find(item => item.id === decision.selectedVersionId)
  if (!target || !version || version.status !== 'done') return
  decision.batch.adoptedVersionId = version.id
  target.activeVersionId = version.id
  target.title = version.type === 'image' ? '图片探索' : '视频探索'
  if (continueToNext) newCardFrom(target, version, decision.batch)
  pendingDecision.value = null
}
function decisionPath(index: number, count: number) {
  const targets = count === 1 ? [[720, 260]] : count === 2 ? [[720, 160], [720, 360]] : [[650, 145], [850, 145], [650, 375], [850, 375]]
  const [x, y] = targets[index] ?? targets[0]
  return `M 300 260 C 430 260, ${x - 150} ${y}, ${x} ${y}`
}

function openHistory(step: CreationCard) {
  historyStepId.value = step.id
  historySelectedVersionId.value = step.activeVersionId
}
function closeHistory() { historyStepId.value = null; historySelectedVersionId.value = undefined }
function markVideoReady(event: Event) { (event.currentTarget as HTMLVideoElement).dataset.ready = 'true' }
function selectedHistoryVersion() {
  return historyStep.value ? versionsFor(historyStep.value).find(version => version.id === historySelectedVersionId.value) : undefined
}
function setHistoryCurrent() {
  const version = selectedHistoryVersion()
  if (!historyStep.value || !version) return
  historyStep.value.activeVersionId = version.id
  closeHistory()
}
function historyAsNext() {
  const version = selectedHistoryVersion()
  if (!historyStep.value || !version) return
  const cloned = { ...version, id: crypto.randomUUID() }
  newCardFrom(historyStep.value, cloned, initialBatch(cloned))
  closeHistory()
}

function openAssets() { assetsOpen.value = true; mobileAssetsOpen.value = true }
function closeAssets() { assetsOpen.value = false; mobileAssetsOpen.value = false }
function toggleAssetWindowMode() {
  assetFixed.value = !assetFixed.value
  assetPanelPosition.value = null
}
function startAssetPanelDrag(event: PointerEvent) {
  if (assetFixed.value || (event.target as HTMLElement).closest('button, input')) return
  const panel = assetPanelElement.value
  if (!panel) return
  const rect = panel.getBoundingClientRect()
  assetPanelDrag = { offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top }
  assetPanelPosition.value = { left: rect.left, top: rect.top }
  window.addEventListener('pointermove', moveAssetPanel)
  window.addEventListener('pointerup', stopAssetPanelDrag, { once: true })
}
function moveAssetPanel(event: PointerEvent) {
  if (!assetPanelDrag || !assetPanelElement.value) return
  const rect = assetPanelElement.value.getBoundingClientRect()
  assetPanelPosition.value = {
    left: Math.max(8, Math.min(window.innerWidth - rect.width - 8, event.clientX - assetPanelDrag.offsetX)),
    top: Math.max(8, Math.min(window.innerHeight - rect.height - 8, event.clientY - assetPanelDrag.offsetY)),
  }
}
function stopAssetPanelDrag() {
  assetPanelDrag = null
  window.removeEventListener('pointermove', moveAssetPanel)
}
function annotationPosition() {
  const anchor = activeStep.value
  return { x: (anchor?.x ?? 100) + 40, y: (anchor?.y ?? 170) + STEP_HEIGHT + 56 }
}
function addTextAnnotation() {
  if (currentLayer.value.locked) return
  const position = annotationPosition()
  const note: TextAnnotation = { kind: 'text', id: nextItemId(), ...position, text: '双击编辑文字' }
  annotations.value.push(note)
  selectedItemIds.value = [note.id]
  focusedStepId.value = null
  focusedGroupId.value = null
}
function addAsset(asset: typeof assets[number]) {
  if (currentLayer.value.locked) return
  const version: MediaVersion = { id: crypto.randomUUID(), type: asset.type, title: asset.title, src: asset.src, prompt: '', status: 'done' }
  const rightmost = steps.value.reduce<CreationCard | undefined>((right, step) => !right || step.x > right.x ? step : right, undefined)
  const step: CreationCard = { kind: 'creation', id: Date.now(), title: asset.title, x: rightmost ? rightmost.x + STEP_GAP : 100, y: rightmost?.y ?? 170, activeVersionId: version.id, batches: [initialBatch(version)], draft: initialDraft(asset.type, '') }
  steps.value.push(step)
  activeStepId.value = step.id
  focusedStepId.value = step.id
  nextTick(resetView)
}
function useCollection(group: GroupCard) {
  const output = group.outputs.find(item => item.id === group.defaultOutputId) ?? group.outputs[0]
  if (!output?.cardIds.length) {
    groupMessage.value = '该集合还没有可用的 Output'
    return
  }
  createFromGroupOutput(group, output)
}
function setCollectionSharing(group: GroupCard, sharing: GroupCard['sharing']) {
  group.sharing = sharing
}
function addReference(reference: Omit<ReferenceInput, 'id'>, key: string) {
  if (draft.value.references.length >= MAX_REFERENCE_INPUTS || draft.value.references.some(item => item.id === key)) return false
  draft.value.references.push({ ...reference, id: key })
  referencePickerOpen.value = false
  return true
}
function addStepReference(step: CreationCard, layer = currentLayer.value) {
  const version = activeVersion(step)
  if (version) addReference({ source: 'canvas', type: version.type, title: layer.id === activeLayerId.value ? version.title : `${layer.name} · ${version.title}`, src: version.src }, `canvas-${layer.id}-${version.id}`)
}
function addAssetReference(asset: typeof assets[number]) { addReference({ source: 'asset', type: asset.type, title: asset.title, src: asset.src }, `asset-${asset.src}`) }
function removeReference(id: string) { draft.value.references = draft.value.references.filter(reference => reference.id !== id) }
function uploadReferences(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files ?? [])
  files.forEach(file => {
    if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) return
    const src = URL.createObjectURL(file)
    if (addReference({ source: 'upload', type: file.type.startsWith('video/') ? 'video' : 'image', title: file.name, src }, `upload-${crypto.randomUUID()}`)) uploadedUrls.add(src)
    else URL.revokeObjectURL(src)
  })
  ;(event.target as HTMLInputElement).value = ''
}

function releaseStepFocus(event: KeyboardEvent) {
  if (event.key !== 'Escape' || pendingDecision.value || historyStep.value) return
  if (activeGroup.value) leaveGroup()
  else {
    focusedStepId.value = null
    focusedGroupId.value = null
    selectedItemIds.value = []
  }
}

interface PersistedBoardState {
  snapshotVersion: number
  layers: BoardLayer[]
  activeLayerId: string
  viewport?: { x: number; y: number; zoom: number }
}

function boardSnapshot(): PersistedBoardState {
  return JSON.parse(JSON.stringify({ snapshotVersion: BOARD_SNAPSHOT_VERSION, layers: layers.value, activeLayerId: activeLayerId.value, viewport: boardViewport.value }))
}
function localBoardKey() { return `production-board:${boardId}` }
function saveLocalBoard(state: PersistedBoardState) {
  localStorage.setItem(localBoardKey(), JSON.stringify(state))
}
function loadLocalBoard(): PersistedBoardState | null {
  try { return JSON.parse(localStorage.getItem(localBoardKey()) || 'null') } catch { return null }
}
async function loadSnapshots() {
  const response = await fetch(`/api/api-proxy/production-boards/${encodeURIComponent(boardId)}/snapshots`)
  if (!response.ok) throw new Error('snapshot list failed')
  snapshots.value = (await response.json()).snapshots || []
}
async function toggleSnapshots() {
  snapshotsOpen.value = !snapshotsOpen.value
  if (snapshotsOpen.value) {
    try { await loadSnapshots() } catch { snapshots.value = [] }
  }
}
async function createSnapshot() {
  const name = `快照 ${new Date().toLocaleString('zh-CN', { hour12: false })}`
  const response = await fetch(`/api/api-proxy/production-boards/${encodeURIComponent(boardId)}/snapshots`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, state: boardSnapshot() }),
  })
  if (!response.ok) throw new Error('snapshot failed')
  await loadSnapshots()
}
async function restoreSnapshot(snapshotId: number) {
  const response = await fetch(`/api/api-proxy/production-boards/${encodeURIComponent(boardId)}/snapshots/${snapshotId}`)
  if (!response.ok) throw new Error('snapshot restore failed')
  if (applyBoardState((await response.json()).state)) queueBoardSave()
}
function applyBoardState(state: PersistedBoardState | null) {
  if (state?.snapshotVersion !== BOARD_SNAPSHOT_VERSION || !state.layers?.length) return false
  applyingRemoteState = true
  state.layers.forEach(layer => layer.groups.forEach(normalizeGroup))
  layers.value = state.layers
  activeLayerId.value = state.layers.some(layer => layer.id === state.activeLayerId) ? state.activeLayerId : state.layers[0].id
  renderedLayerId.value = activeLayerId.value
  const savedViewport = state.viewport ?? currentLayer.value.viewport
  if (savedViewport && Number.isFinite(savedViewport.x) && Number.isFinite(savedViewport.y) && Number.isFinite(savedViewport.zoom)) {
    boardViewport.value = { ...savedViewport }
    hasSavedBoardViewport.value = true
  }
  const first = currentLayer.value.rootSteps[0]
  activeStepId.value = first?.id ?? 0
  focusedStepId.value = first?.id ?? null
  groupStack.value = []
  activeGroupId.value = null
  applyingRemoteState = false
  saveState.value = 'saved'
  return true
}
function normalizeGroup(group: GroupCard) {
  group.groups ??= []
  group.inputNodes ??= []
  group.outputNodes ??= []
  group.outputs ??= []
  group.incomingSources ??= []
  group.boundaryLinks ??= []
  group.viewport ??= { x: 0, y: 0, zoom: 1 }
  group.viewportReady ??= false
  group.sharing ??= 'personal'
  group.outputs.forEach(output => {
    const legacy = output as GroupOutput & { cardId?: number }
    if (!Array.isArray(output.cardIds)) output.cardIds = legacy.cardId ? [legacy.cardId] : []
    if (!group.outputNodes.some(node => node.outputId === output.id)) group.outputNodes.push({ kind: 'output', id: nextItemId(), x: 520, y: 80 + group.outputNodes.length * 96, outputId: output.id })
  })
  group.groups.forEach(normalizeGroup)
}
async function saveBoard() {
  window.clearTimeout(saveTimer)
  saveState.value = 'saving'
  const state = boardSnapshot()
  try { saveLocalBoard(state) } catch { saveState.value = 'error'; return }
  try {
    const response = await fetch(`/api/api-proxy/production-boards/${encodeURIComponent(boardId)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ state, client_id: boardClientId }),
    })
    if (!response.ok) throw new Error('save failed')
    saveState.value = 'saved'
  } catch { saveState.value = 'local' }
}
function queueBoardSave() {
  if (applyingRemoteState) return
  saveState.value = 'saving'
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(() => { void saveBoard() }, 800)
}
function connectBoardSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  boardSocket = new WebSocket(`${protocol}//${window.location.host}/api/api-proxy/production-boards/${encodeURIComponent(boardId)}/ws`)
  boardSocket.onmessage = event => {
    try {
      const message = JSON.parse(event.data)
      if (message.type === 'state' && message.source !== boardClientId) applyBoardState(message.state)
    } catch { /* ignore malformed collaboration messages */ }
  }
}
async function loadBoard() {
  try {
    const response = await fetch(`/api/api-proxy/production-boards/${encodeURIComponent(boardId)}`)
    if (!response.ok) throw new Error('load failed')
    if (!applyBoardState((await response.json()).state)) queueBoardSave()
  } catch {
    if (applyBoardState(loadLocalBoard())) saveState.value = 'local'
    else queueBoardSave()
  }
}
async function shareBoard() {
  const url = new URL(window.location.href)
  url.hash = `/create?board=${encodeURIComponent(boardId)}`
  try { await navigator.clipboard.writeText(url.toString()) } catch { window.prompt('复制此协作链接', url.toString()) }
}

watch([layers, activeLayerId], queueBoardSave, { deep: true, flush: 'sync' })

onMounted(async () => {
  window.addEventListener('keydown', releaseStepFocus)
  window.addEventListener('pointerdown', closeLayerContextMenu)
  if (canvasElement.value) {
    canvasResizeObserver = new ResizeObserver(entries => {
      const box = entries[0]?.contentRect
      if (box) canvasSize.value = { width: Math.round(box.width), height: Math.round(box.height) }
    })
    canvasResizeObserver.observe(canvasElement.value)
  }
  await loadBoard()
  connectBoardSocket()
  await nextTick()
  if (hasSavedBoardViewport.value) await flow.setViewport(boardViewport.value, { duration: 0 })
  else await resetView()
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', releaseStepFocus)
  window.removeEventListener('pointerdown', closeLayerContextMenu)
  window.removeEventListener('pointermove', moveLayerPanel)
  window.clearTimeout(handoffTimer)
  window.clearTimeout(handoffFallbackTimer)
  window.clearTimeout(saveTimer)
  if (saveState.value === 'saving' && !applyingRemoteState) void saveBoard()
  boardSocket?.close()
  canvasResizeObserver?.disconnect()
  uploadedUrls.forEach(url => URL.revokeObjectURL(url))
})
</script>

<template>
  <main class="production-board">
    <header class="board-head">
      <div class="board-identity"><span v-if="!activeGroup">夏日短片</span><span v-else class="board-breadcrumb"><button @click="leaveGroup">主画布</button><i>/</i>{{ activeGroup.title }}</span><h1>制作板</h1></div>
      <div class="head-actions"><span class="saved" :class="saveState"><i />{{ saveState === 'saving' ? '保存中' : saveState === 'local' ? '本地已保存' : saveState === 'error' ? '保存失败' : '已保存' }}</span><button @click="toggleSnapshots">快照</button><button @click="shareBoard">分享</button><button class="export">导出</button><section v-if="snapshotsOpen" class="snapshot-menu"><header><strong>画板快照</strong><button @click="createSnapshot">创建快照</button></header><p v-if="!snapshots.length">暂无服务端快照</p><button v-for="snapshot in snapshots" :key="snapshot.id" @click="restoreSnapshot(snapshot.id)"><span>{{ snapshot.name }}</span><small>恢复</small></button></section></div>
    </header>

    <section ref="canvasElement" class="canvas" :class="{ 'brush-mode': canvasTool === 'brush' }" @pointerdown.capture="prepareCanvasSelection" @pointermove.capture="extendBrush" @pointerup.capture="finishBrush">
      <nav class="creation-tools" aria-label="画布工具" @pointerdown.stop>
        <button :class="{ active: canvasTool === 'select' }" title="左键拖拽框选；Shift 复选" @click="canvasTool = 'select'"><Pointer /></button><button title="添加图片" @click="openAssets"><Picture /></button><button title="添加文字" @click="addTextAnnotation"><EditPen /></button><button :class="{ active: canvasTool === 'brush' }" title="画笔标注：在画布空白处拖拽绘制" @click="canvasTool = canvasTool === 'brush' ? 'select' : 'brush'"><Plus /></button><button v-if="!activeGroup" :disabled="selectedCreationCount < 2" title="将选中卡片打组" @click="packSelectedCards"><FolderAdd /></button>
      </nav>
      <LayerBackdrop v-for="item in layerCacheViews" :key="item.layer.id" :layer="item.layer" :links="item.links" :depth="item.depth" :visible="item.visible" :priority="item.layer.id === activeLayerId" :transitioning="item.transitioning" :fade-out="handoffFading" :outgoing-scale="outgoingLayerScale" :render-level="item.renderLevel" :blur-enabled="backdropBlurEnabled" :viewport="item.viewport" :width="canvasSize.width" :height="canvasSize.height" :render-revision="item.revision" :moving="isCanvasMoving" :dpr="item.dpr" />
      <div class="active-layer-stage" :class="{ switching: layerSwitching, entering: handoffFading }" :style="{ '--incoming-scale': incomingLayerScale }">
      <VueFlow id="production-board" class="thought-flow" :nodes="flowNodes" :edges="flowEdges" :min-zoom=".45" :max-zoom="1.5" only-render-visible-elements :nodes-connectable="false" :elements-selectable="true" :edges-updatable="false" :selection-key-code="true" selection-mode="full" connection-mode="loose" :pan-on-drag="[1, 2]" zoom-on-scroll zoom-on-pinch :zoom-on-double-click="false" @init="resetView" @move-start="setCanvasMoving(true)" @move="updateBoardViewport" @move-end="setCanvasMoving(false)" @pane-click="handlePaneClick" @selection-end="finishCanvasSelection" @node-click="handleNodeClick" @nodes-change="handleNodesChange" @node-drag-start="setCanvasMoving(true)" @node-drag="syncStepPosition" @node-drag-stop="handleNodeDragStop">
        <template #node-thought="{ data }">
          <Handle id="left" type="source" :position="Position.Left" class="trail-handle" />
          <Handle id="right" type="source" :position="Position.Right" class="trail-handle" />
          <Handle id="top" type="source" :position="Position.Top" class="trail-handle" />
          <Handle id="bottom" type="source" :position="Position.Bottom" class="trail-handle" />
          <article class="thought-step" :class="{ active: !data.background && data.step.id === focusedStepId, background: data.background, generating: data.version?.status === 'generating', failed: data.version?.status === 'error' }" @click.stop="!data.background && selectBoardItem(data.step, $event)" @dblclick.stop="!data.background && data.version?.status === 'done' && openPreview(data.version)">
            <div class="step-tools"><button v-if="activeGroup" class="nodrag" :class="{ active: isGroupOutput(data.step) }" :title="isGroupOutput(data.step) ? '取消输出' : '设为输出'" @click.stop="toggleGroupOutput(data.step)"><Upload /></button><button class="nodrag" title="使用为参考" @click.stop="addStepReference(data.step)"><Star /></button><button class="nodrag" title="更多"><MoreFilled /></button></div>
            <div class="step-media"><div v-if="data.version?.status === 'generating'" class="generation-pulse"><i /><span>正在生成</span><small>连接已建立，等待真实结果</small></div><div v-else-if="data.version?.status === 'error'" class="generation-error"><strong>生成失败</strong><span>{{ data.version.error || '请检查模型配置或参考素材' }}</span></div><template v-else-if="data.version?.type === 'video'"><video :src="data.version.src" muted loop autoplay @loadeddata="markVideoReady($event); markHandoffMediaReady(data.version?.id)" @error="markHandoffMediaReady(data.version?.id)" /><span class="video-monitor"><VideoCamera /><em>VIDEO PREVIEW</em></span></template><img v-else :src="data.version?.src" :alt="data.step.title" loading="lazy" decoding="async" :title="`保留原图，最高支持 ${MAX_IMAGE_DIMENSION}px`" @load="markHandoffMediaReady(data.version?.id)" @error="markHandoffMediaReady(data.version?.id)" /><span class="media-kind"><VideoCamera v-if="data.version?.type === 'video'" /><Picture v-else />{{ data.version?.type === 'video' ? '视频' : '图片' }}</span><b v-if="data.version?.type === 'video' && data.version.status === 'done'">00:05</b></div>
            <button class="history-entry nodrag" @click.stop="openHistory(data.step)">历史 {{ historyCount(data.step) }}</button>
            <div v-if="data.step.id === focusedStepId" class="step-detail"><span>{{ data.step.draft.modelId === 'smart' ? '智能匹配' : selectedModel.label }}</span><span>{{ data.step.draft.mode === 'video' ? '视频制作' : '图片制作' }}</span></div>
          </article>
        </template>
        <template #node-group="{ data }">
          <Handle id="left" type="source" :position="Position.Left" class="trail-handle" /><Handle id="right" type="source" :position="Position.Right" class="trail-handle" />
          <article class="group-node" :class="{ active: !data.background && data.group.id === focusedGroupId, background: data.background }" @click.stop="!data.background && selectBoardItem(data.group, $event)" @dblclick.stop="!data.background && enterGroup(data.group)">
            <div class="group-cover"><video v-if="defaultGroupVersion(data.group)?.type === 'video'" :src="defaultGroupVersion(data.group)?.src" muted @loadeddata="markHandoffMediaReady(defaultGroupVersion(data.group)?.id)" @error="markHandoffMediaReady(defaultGroupVersion(data.group)?.id)" /><img v-else-if="defaultGroupVersion(data.group)" :src="defaultGroupVersion(data.group)?.src" alt="" @load="markHandoffMediaReady(defaultGroupVersion(data.group)?.id)" @error="markHandoffMediaReady(defaultGroupVersion(data.group)?.id)" /><span v-else><FolderOpened />暂无输出</span></div>
            <header><div><FolderOpened /><strong>{{ data.group.title }}</strong></div><small>{{ data.group.children.length }} 内容 · {{ data.group.outputs.length }} 输出</small></header>
            <div class="group-output-strip"><button v-for="item in data.outputs.slice(0, 3)" :key="item.output.id" class="nodrag" :class="{ active: item.output.id === data.group.defaultOutputId }" :title="item.output.name" @click.stop="setDefaultOutput(data.group, item.output)"><video v-if="item.version.type === 'video'" :src="item.version.src" muted /><img v-else :src="item.version.src" alt="" /></button><span v-if="data.outputs.length > 3">+{{ data.outputs.length - 3 }}</span><button class="group-enter nodrag" title="进入子面板" @click.stop="enterGroup(data.group)"><ArrowUp /></button></div>
          </article>
        </template>
        <template #node-group-input="{ data }">
          <Handle id="right" type="source" :position="Position.Right" class="trail-handle" />
          <article class="group-port input-port" @click.stop="selectBoardItem(data.port, $event)"><small>GROUP INPUT</small><strong>{{ data.port.name }}</strong><span>共享外部参考包</span></article>
        </template>
        <template #node-group-output="{ data }">
          <Handle id="left" type="target" :position="Position.Left" class="trail-handle" />
          <Handle id="right" type="source" :position="Position.Right" class="trail-handle" />
          <article class="group-port output-port" @click.stop="selectBoardItem(data.port, $event)"><small>GROUP OUTPUT</small><strong>{{ data.output?.name ?? '输出' }}</strong><span>{{ data.output?.cardIds.length ?? 0 }} 个参考</span></article>
        </template>
        <template #node-text-annotation="{ data }">
          <article class="text-annotation" :class="{ background: data.background }" @click.stop="!data.background && selectBoardItem(data.note, $event)"><textarea v-model="data.note.text" class="nodrag" aria-label="文字标注" :readonly="data.background" @pointerdown.stop /></article>
        </template>
        <template #node-brush-annotation="{ data }">
          <article class="brush-annotation" :class="{ background: data.background }" @click.stop="!data.background && selectBoardItem(data.note, $event)"><svg viewBox="0 0 190 112" aria-label="画笔标注"><path :d="data.note.path" /></svg></article>
        </template>
        <template #edge-thought="{ data }">
          <defs><linearGradient :id="`trail-${data.id}`" gradientUnits="userSpaceOnUse" :x1="data.p0.x" :y1="data.p0.y" :x2="data.p2.x" :y2="data.p2.y"><stop offset="0" :stop-color="data.sourceColor" stop-opacity=".62" /><stop offset=".32" :stop-color="data.sourceColor" :stop-opacity="data.shoulderOpacity" /><stop offset=".5" :stop-color="data.targetColor" :stop-opacity="data.centerOpacity" /><stop offset=".68" :stop-color="data.targetColor" :stop-opacity="data.shoulderOpacity" /><stop offset="1" :stop-color="data.targetColor" stop-opacity=".62" /></linearGradient></defs>
          <g class="thought-trail" :class="{ active: !data.background && (data.sourceId === focusedStepId || data.targetId === focusedStepId || data.sourceId === focusedGroupId || data.targetId === focusedGroupId), background: data.background }"><path class="trajectory-shadow" :d="data.d" /><path class="trajectory-stroke" :d="data.d" :stroke="`url(#trail-${data.id})`" /><polygon class="trajectory-arrow" :points="data.arrowPoints" :fill="data.targetColor" /></g>
        </template>
      </VueFlow>
      </div>
      <div v-if="activeGroup" class="group-port-toolbar"><span class="group-path"><button v-for="(group, index) in groupStack" :key="group.id" @click="leaveToGroup(index)">{{ group.title }}</button></span><button :disabled="!groupInputVersions(activeGroup).length" title="把 Group 输入包加入当前创作" @click="addGroupInputReferences"><Star /> Use input</button><button @click="addGroupInputNode"><ArrowDown /> Input</button><button @click="addGroupOutputNode"><Upload /> Output</button><button :disabled="selectedCreationCount < 2" @click="packSelectedCards"><FolderAdd /> Group</button></div>
      <div v-if="groupMessage" class="group-notice">{{ groupMessage }}</div>
      <BoardMinimap v-if="!activeGroup" :layers="layers" :active-layer-id="activeLayerId" :viewport="boardViewport" :canvas-width="canvasSize.width" :canvas-height="canvasSize.height" :zoom-percent="Math.round(scale * 100)" @navigate="navigateFromMinimap" @select-layer="selectLayerFromMinimap" @zoom-out="zoomBy(-.1)" @zoom-in="zoomBy(.1)" @fit="resetView" />
    </section>

    <aside ref="layerPanelElement" class="layer-panel" :class="{ floating: layerPanelPosition }" :style="layerPanelPosition ? { left: `${layerPanelPosition.left}px`, top: `${layerPanelPosition.top}px` } : undefined" @pointerdown.stop>
      <header title="拖动图层面板" @pointerdown="startLayerPanelDrag"><div><strong>图层</strong><span>{{ layers.length }}/10</span></div><button :disabled="!canAddLayer" @click="addLayer">＋ 图层</button></header>
      <section v-for="layer in [...layers].reverse()" :key="layer.id" :class="{ active: layer.id === activeLayerId }" @click="handleLayerRowClick($event, layer)" @contextmenu="openLayerContextMenu($event, layer)">
        <div class="layer-row"><input v-if="renamingLayerId === layer.id" v-model="layer.name" class="layer-name-editor nodrag" aria-label="图层名称" @pointerdown.stop @click.stop @keydown.enter.prevent="finishLayerRename(layer)" @keydown.esc.prevent="finishLayerRename(layer)" @blur="finishLayerRename(layer)" /><span v-else class="layer-name">{{ layer.name }}</span><i :class="{ hidden: !layer.visible }">{{ layer.visible ? '◉' : '○' }}</i><small v-if="layer.locked">锁</small></div>
      </section>
    </aside>
    <div v-if="layerContextMenu && contextLayer" class="layer-context-menu" :style="{ left: `${layerContextMenu.x}px`, top: `${layerContextMenu.y}px` }" @pointerdown.stop>
      <button @click="beginLayerRename(contextLayer)">重命名</button>
      <button :disabled="contextLayer.id === activeLayerId" @click="contextLayer.visible = !contextLayer.visible; closeLayerContextMenu()">{{ contextLayer.visible ? '隐藏图层' : '显示图层' }}</button>
      <button @click="contextLayer.locked = !contextLayer.locked; closeLayerContextMenu()">{{ contextLayer.locked ? '解除锁定' : '锁定图层' }}</button>
      <button class="danger" :disabled="layers.length === 1 || !layerIsEmpty(contextLayer)" @click="removeLayer(contextLayer); closeLayerContextMenu()">删除图层</button>
    </div>

    <button class="mobile-assets" title="打开素材库" @click="openAssets"><Picture /></button>
    <aside ref="assetPanelElement" class="asset-panel" :class="{ collapsed: !assetsOpen, floating: !assetFixed, 'mobile-open': mobileAssetsOpen }" :style="assetPanelPosition ? { left: `${assetPanelPosition.left}px`, top: `${assetPanelPosition.top}px`, right: 'auto', bottom: 'auto' } : undefined" @pointerdown.stop>
      <button v-if="!assetsOpen" class="asset-rail" title="展开素材库" @click="openAssets"><Picture /></button>
      <template v-else>
        <header class="asset-window-head" :class="{ draggable: !assetFixed }" @pointerdown="startAssetPanelDrag"><div><small>项目共享资源</small><strong>素材库</strong><span>{{ assets.length }} 项</span></div><div class="asset-actions"><button :title="assetFixed ? '浮动窗口' : '固定到右侧'" @click="toggleAssetWindowMode"><Unlock v-if="assetFixed" /><Lock v-else /></button><button title="收起素材库" @click="closeAssets"><ArrowDown /></button></div></header>
        <div class="asset-window-body">
          <aside class="asset-categories"><strong>项目素材</strong><button :class="{ active: assetFilter === 'all' }" @click="assetFilter = 'all'">全部素材 <span>{{ assets.length }}</span></button><button :class="{ active: assetFilter === 'image' }" @click="assetFilter = 'image'">图片 <span>{{ assetCounts.image }}</span></button><button :class="{ active: assetFilter === 'video' }" @click="assetFilter = 'video'">视频 <span>{{ assetCounts.video }}</span></button><i /><strong>集合</strong><button :class="{ active: assetFilter === 'reference-set' }" @click="assetFilter = 'reference-set'">参考集 <span>{{ collectionCounts.reference }}</span></button><button :class="{ active: assetFilter === 'process-set' }" @click="assetFilter = 'process-set'">处理集 <span>{{ collectionCounts.process }}</span></button><i /><strong>共享</strong><button :class="{ active: assetFilter === 'personal' }" @click="assetFilter = 'personal'">个人 <span>{{ collectionCounts.personal }}</span></button><button :class="{ active: assetFilter === 'team' }" @click="assetFilter = 'team'">团队 <span>{{ collectionCounts.team }}</span></button><i /><small>Group 会自动进入集合并实时同步</small></aside>
          <section class="asset-browser"><div class="asset-browser-tools"><label class="asset-search"><Search /><input v-model="assetSearch" :placeholder="collectionMode ? '搜索集合' : '搜索项目素材'" /></label><button v-if="!collectionMode" class="upload"><Upload />上传</button></div><template v-if="collectionMode"><div v-if="visibleCollections.length" class="asset-grid collection-grid"><button v-for="item in visibleCollections" :key="item.group.id" :class="{ selected: selectedCollection?.group.id === item.group.id }" @click="selectedCollectionId = item.group.id" @dblclick="useCollection(item.group)"><video v-if="defaultGroupVersion(item.group)?.type === 'video'" :src="defaultGroupVersion(item.group)?.src" muted /><img v-else-if="defaultGroupVersion(item.group)" :src="defaultGroupVersion(item.group)?.src" :alt="item.group.title" loading="lazy" decoding="async" /><span v-else class="collection-placeholder"><FolderOpened /></span><small>{{ item.group.title }}</small><em>{{ item.kind === 'process-set' ? '处理集' : '参考集' }}</em></button></div><div v-else class="asset-empty">暂无匹配的集合</div></template><template v-else><div v-if="visibleAssets.length" class="asset-grid"><button v-for="asset in visibleAssets" :key="asset.title" :class="{ selected: selectedAsset === asset }" @click="selectedAsset = asset" @dblclick="addAsset(asset)"><video v-if="asset.type === 'video'" :src="asset.src" muted /><img v-else :src="asset.src" :alt="asset.title" loading="lazy" decoding="async" /><small>{{ asset.title }}</small><em>{{ asset.type === 'video' ? '视频' : '图片' }}</em></button></div><div v-else class="asset-empty">没有匹配的素材</div></template></section>
        </div>
        <footer v-if="collectionMode && selectedCollection" class="asset-inspector"><div class="asset-preview"><video v-if="defaultGroupVersion(selectedCollection.group)?.type === 'video'" :src="defaultGroupVersion(selectedCollection.group)?.src" muted /><img v-else-if="defaultGroupVersion(selectedCollection.group)" :src="defaultGroupVersion(selectedCollection.group)?.src" :alt="selectedCollection.group.title" /><FolderOpened v-else /></div><div><small>{{ selectedCollection.kind === 'process-set' ? '处理集' : '参考集' }}</small><strong>{{ selectedCollection.group.title }}</strong><span>{{ selectedCollection.group.outputs.length }} 个 Output · 实时跟随画板</span></div><div class="collection-sharing"><button :class="{ active: selectedCollection.group.sharing === 'personal' }" @click="setCollectionSharing(selectedCollection.group, 'personal')">个人</button><button :class="{ active: selectedCollection.group.sharing === 'team' }" @click="setCollectionSharing(selectedCollection.group, 'team')">团队</button></div><button class="primary" :disabled="!selectedCollection.group.outputs.length" @click="useCollection(selectedCollection.group)"><Plus />加入画板</button></footer><footer v-else-if="selectedAsset" class="asset-inspector"><div class="asset-preview"><video v-if="selectedAsset.type === 'video'" :src="selectedAsset.src" muted /><img v-else :src="selectedAsset.src" :alt="selectedAsset.title" /></div><div><small>{{ selectedAsset.type === 'video' ? '视频素材' : '图片素材' }}</small><strong>{{ selectedAsset.title }}</strong><span>项目素材 · 所有画板可用</span></div><button class="primary" @click="addAsset(selectedAsset)"><Plus />加入画板</button></footer>
      </template>
    </aside>

    <section class="control-dock" :class="{ collapsed: !controlsOpen, 'group-mode': selectedGroup }" @pointerdown.stop>
      <button v-if="!controlsOpen" class="dock-restore" @click="controlsOpen = true"><span class="restore-mode">{{ selectedGroup ? '子面板' : '当前创作' }}</span><i class="restore-thumb"><template v-if="selectedGroup"><video v-if="defaultGroupVersion(selectedGroup)?.type === 'video'" :src="defaultGroupVersion(selectedGroup)?.src" muted /><img v-else-if="defaultGroupVersion(selectedGroup)" :src="defaultGroupVersion(selectedGroup)?.src" /><FolderOpened v-else /></template><template v-else><video v-if="activeVersion(activeStep)?.type === 'video'" :src="activeVersion(activeStep)?.src" muted /><img v-else :src="activeVersion(activeStep)?.src" /></template></i><span class="restore-copy"><strong>{{ selectedGroup?.title ?? activeStep.title }}</strong><small>{{ selectedGroup ? `${selectedGroup.children.length} 内容 · ${selectedGroup.outputs.length} 输出` : `${draft.references.length} 个输入 · ${selectedModel.label}` }}</small></span><ArrowUp /></button>
      <template v-else-if="selectedGroup">
        <div class="dock-context group-context"><span>子面板</span><input v-model="selectedGroup.title" aria-label="子面板名称" /><small>{{ selectedGroup.children.length }} 内容 · {{ selectedGroup.outputs.length }} 输出</small></div>
        <div class="group-output-manager"><div v-for="(output, index) in selectedGroup.outputs" :key="output.id" class="group-output-item" :class="{ active: output.id === selectedGroup.defaultOutputId }" @click="setDefaultOutput(selectedGroup, output)"><i><video v-if="groupOutputVersion(selectedGroup, output)?.type === 'video'" :src="groupOutputVersion(selectedGroup, output)?.src" muted /><img v-else :src="groupOutputVersion(selectedGroup, output)?.src" /></i><input v-model="output.name" :aria-label="`输出 ${index + 1} 名称`" @click.stop /><span><button title="前移" @click.stop="moveGroupOutput(selectedGroup, output, -1)">←</button><button title="后移" @click.stop="moveGroupOutput(selectedGroup, output, 1)">→</button></span></div><div v-if="!selectedGroup.outputs.length" class="group-output-empty">进入子面板，将卡片设为输出</div></div>
        <div class="group-panel-actions"><span>{{ groupMessage }}</span><button class="secondary" @click="enterGroup(selectedGroup)"><FolderOpened />进入子面板</button><button class="primary" :disabled="!selectedGroupOutput || connectionCount >= MAX_CONNECTIONS" @click="selectedGroupOutput && createFromGroupOutput(selectedGroup, selectedGroupOutput)">从输出新建</button><button class="secondary danger" @click="dissolveGroup(selectedGroup)">解散</button><button class="collapse" title="收起创作台" @click="controlsOpen = false"><ArrowDown /></button></div>
      </template>
      <template v-else>
        <div v-if="advancedOpen" class="advanced-popover">
          <header><strong>高级参数</strong><button title="关闭" @click="advancedOpen = false"><Close /></button></header>
          <div class="advanced-grid"><label>生成质量<select v-model="draft.quality"><option value="draft">草稿</option><option value="standard">标准</option><option value="high">高质量</option></select></label><label class="range-field"><span>创意强度 <b>{{ draft.creativity }}</b></span><input v-model="draft.creativity" type="range" min="0" max="100" /></label><label class="range-field"><span>提示词相关度 <b>{{ draft.promptWeight }}</b></span><input v-model="draft.promptWeight" type="range" min="0" max="100" /></label><label>随机种子<input v-model.number="draft.seed" type="number" placeholder="-1 为随机" /></label><label class="negative-field">负向提示词<input v-model="draft.negativePrompt" placeholder="不希望画面中出现的内容" /></label></div>
        </div>
        <div class="reference-bar">
          <div class="reference-rail"><div class="reference-list"><button v-for="(reference, index) in draft.references" :key="reference.id" class="reference-item" :class="{ invalid: invalidReferenceIds.has(reference.id) }" :title="reference.title"><video v-if="reference.type === 'video'" :src="reference.src" muted /><img v-else :src="reference.src" :alt="reference.title" /><span>{{ reference.type === 'video' ? '视频' : '图片' }}</span><i v-if="index >= activeInputLimit">超额</i><b title="移除输入" @click.stop="removeReference(reference.id)"><Close /></b></button><button class="reference-add" title="添加图片" :disabled="draft.references.length >= MAX_REFERENCE_INPUTS" @click="referencePickerOpen = !referencePickerOpen"><Picture /><Plus /></button></div><div class="rail-fade" /><span class="reference-count" :class="{ over: isOverModelLimit }">{{ draft.references.length }}/{{ activeInputLimit }}</span>
            <div v-if="referencePickerOpen" class="reference-picker"><strong>添加输入</strong><div><span>当前层与下层创作</span><button v-for="item in referenceSteps" :key="`${item.layer.id}-${item.step.id}`" @click="addStepReference(item.step, item.layer)"><small v-if="item.layer.id !== activeLayerId">{{ item.layer.name }} · </small>{{ item.step.title }}</button></div><div v-if="availableGroupOutputs.length"><span>子面板输出</span><button v-for="item in availableGroupOutputs" :key="item.output.id" @click="addGroupOutputReference(item.group, item.output)">{{ item.group.title }} · {{ item.output.name }}</button></div><div><span>素材库</span><button v-for="asset in assets" :key="asset.title" @click="addAssetReference(asset)">{{ asset.title }}</button></div><label class="reference-upload"><Upload />上传图片或视频<input type="file" accept="image/*,video/*" multiple @change="uploadReferences" /></label></div>
          </div>
          <div class="mode-switch"><button :class="{ active: draft.mode === 'image' }" @click="draft.mode = 'image'">图片</button><button :class="{ active: draft.mode === 'video' }" @click="draft.mode = 'video'">视频</button></div>
        </div>
        <div class="composer-input"><textarea v-model="draft.prompt" :placeholder="draft.mode === 'image' ? '描述这次创作想解决的画面问题…' : '描述这次创作的动作、运镜与节奏…'" /></div>
        <div class="composer-bottom"><div class="composer-meta"><label><select v-model="draft.modelId"><option v-for="model in modelOptions" :key="model.id" :value="model.id">{{ model.label }}</option></select></label><label><select v-model="draft.ratio"><option>16:9</option><option>1:1</option><option>9:16</option></select></label><label><select v-model.number="draft.generationCount"><option :value="1">1 个</option><option :value="2">2 个</option><option :value="4">4 个</option></select></label><button :class="{ active: advancedOpen }" @click="advancedOpen = !advancedOpen">高级</button></div><div class="composer-footer"><span v-if="isOverModelLimit" class="generation-hint">移除超额素材或切换模型后可生成</span><div class="footer-actions"><button class="generate" :disabled="generationBlocked" @click="createGeneration"><Star /><span>生成{{ draft.mode === 'image' ? '图片' : '视频' }}</span><small>4 积分</small></button><button class="collapse" title="收起创作台" @click="controlsOpen = false"><ArrowDown /></button></div></div></div>
      </template>
    </section>

    <div v-if="pendingDecision" class="modal-layer" @pointerdown.stop>
      <section class="decision-window" role="dialog" aria-modal="true" aria-label="选择生成结果">
        <header><div><small>本次生成决策</small><h2>从 {{ pendingDecision.batch.versions.length }} 个结果中选择</h2></div><button title="关闭并保存到历史" @click="closeDecision"><Close /></button></header>
        <div class="decision-stage">
          <svg viewBox="0 0 1000 520" preserveAspectRatio="none" aria-hidden="true"><path v-for="(_, index) in pendingDecision.batch.versions" :key="index" :d="decisionPath(index, pendingDecision.batch.versions.length)" /></svg>
          <div class="decision-source"><small>来源创作</small><div><video v-if="activeVersion(steps.find(step => step.id === pendingDecision?.sourceCardId)!)?.type === 'video'" :src="activeVersion(steps.find(step => step.id === pendingDecision?.sourceCardId)!)?.src" muted /><img v-else :src="activeVersion(steps.find(step => step.id === pendingDecision?.sourceCardId)!)?.src" /></div><strong>{{ steps.find(step => step.id === pendingDecision?.sourceCardId)?.title }}</strong></div>
          <div class="candidate-grid" :class="`count-${pendingDecision.batch.versions.length}`"><button v-for="version in pendingDecision.batch.versions" :key="version.id" :disabled="version.status !== 'done'" :class="{ selected: pendingDecision.selectedVersionId === version.id, generating: version.status === 'generating', failed: version.status === 'error' }" @click="selectCandidate(version)" @dblclick.stop="version.status === 'done' && openPreview(version)"><video v-if="version.status === 'done' && version.type === 'video'" :src="version.src" muted loop autoplay /><img v-else-if="version.status === 'done'" :src="version.src" :alt="version.title" /><span v-if="version.status === 'generating'">正在提交真实生成任务…</span><span v-else-if="version.status === 'error'">{{ version.error || '生成失败' }}</span><strong>{{ version.title }}</strong></button></div>
        </div>
        <footer><span>未采用结果会保存在当前创作历史中</span><div><button class="secondary" :disabled="!pendingDecision.selectedVersionId" @click="adoptCandidate(false)">采用</button><button class="primary" :disabled="!pendingDecision.selectedVersionId" @click="adoptCandidate(true)">采用并新建 →</button></div></footer>
      </section>
    </div>

    <div v-if="historyStep" class="modal-layer" @pointerdown.stop>
      <section class="history-window" role="dialog" aria-modal="true" aria-label="创作历史">
        <header><div><small>创作历史</small><h2>{{ historyStep.title }} · 历史 {{ historyCount(historyStep) }}</h2></div><button title="关闭" @click="closeHistory"><Close /></button></header>
        <div class="history-batches"><section v-for="(batch, batchIndex) in [...historyStep.batches].reverse()" :key="batch.id"><header><span>批次 {{ historyStep.batches.length - batchIndex }}</span><small>{{ batch.versions.length }} 个结果</small></header><div><button v-for="version in batch.versions" :key="version.id" :class="{ selected: historySelectedVersionId === version.id }" @click="historySelectedVersionId = version.id" @dblclick.stop="openPreview(version)"><video v-if="version.type === 'video'" :src="version.src" muted /><img v-else :src="version.src" :alt="version.title" /><span v-if="historyStep.activeVersionId === version.id">当前</span><strong>{{ version.title }}</strong></button></div></section></div>
        <footer><span>历史版本不会占用画布空间</span><div><button class="secondary" :disabled="!historySelectedVersionId" @click="setHistoryCurrent">设为当前</button><button class="primary" :disabled="!historySelectedVersionId" @click="historyAsNext">作为新创作 →</button></div></footer>
      </section>
    </div>

    <MediaViewer :visible="Boolean(previewVersion)" :item="viewerItem" :show-nav="allActiveVersions.length > 1" @close="previewVersion = null" @prev="movePreview(-1)" @next="movePreview(1)" />
  </main>
</template>

<style scoped>
.production-board{--mint:#d6d6d6;--surface:rgba(17,17,17,.97);--line:rgba(255,255,255,.07);position:relative;height:calc(100vh - 22px);overflow:hidden;background:#0b0b0b;color:rgba(255,255,255,.9)}
.active-layer-stage{position:absolute;z-index:2;inset:0;transform-origin:center}.active-layer-stage>.thought-flow{width:100%;height:100%}.active-layer-stage.switching{opacity:0;transform:scale(var(--incoming-scale));will-change:opacity,transform}.active-layer-stage.switching.entering{opacity:1;transform:scale(1);transition:opacity .22s cubic-bezier(.2,.75,.25,1),transform .22s cubic-bezier(.2,.75,.25,1)}
@media(prefers-reduced-motion:reduce){.active-layer-stage.switching.entering{transition:none}}
button,input,textarea,select{font:inherit}.board-head{position:absolute;z-index:30;inset:0 0 auto;height:56px;padding:0 18px;display:flex;align-items:center;justify-content:space-between;background:rgba(10,10,10,.88);backdrop-filter:blur(18px)}.board-identity,.head-actions{display:flex;align-items:center;gap:13px}.board-identity span,.saved{color:rgba(255,255,255,.3);font-size:10px}.board-identity h1{font-size:15px;font-weight:560}.head-actions button{border:0;background:transparent;color:rgba(255,255,255,.5);font-size:10px;cursor:pointer}.head-actions .export{height:29px;padding:0 12px;border-radius:7px;background:rgba(255,255,255,.13);color:#f2f2f2}.saved{display:flex;gap:6px}.saved i{width:4px;height:4px;border-radius:50%;background:#8e8e8e}
.canvas{position:absolute;inset:56px 0 0;overflow:hidden;background:#0b0b0b}.thought-flow{width:100%;height:100%;background:#0b0b0b radial-gradient(rgba(255,255,255,.08) .65px,transparent .65px);background-size:24px 24px}.thought-flow :deep(.vue-flow__pane){cursor:grab}.thought-flow :deep(.vue-flow__pane.dragging){cursor:grabbing}.thought-flow :deep(.vue-flow__node-thought){width:286px;border:0;background:transparent}.trail-handle{width:1px!important;height:1px!important;min-width:0!important;min-height:0!important;border:0!important;background:transparent!important;opacity:0;pointer-events:none}.thought-trail{opacity:.72;transition:opacity .18s ease}.thought-trail.active{opacity:1}.thought-trail path{fill:none;stroke-linecap:round;vector-effect:non-scaling-stroke}.trajectory-shadow{stroke:#050505;stroke-width:5;stroke-opacity:.72}.trajectory-stroke{stroke-width:1.6}.thought-trail.active .trajectory-stroke{filter:drop-shadow(0 0 3px rgba(255,255,255,.2))}.creation-tools{position:absolute;z-index:6;left:14px;top:14px;padding:4px;display:flex;flex-direction:column;gap:2px;border-radius:8px;background:rgba(17,17,17,.72)}.creation-tools button,.canvas-tools button{width:28px;height:28px;padding:7px;border:0;border-radius:6px;background:transparent;color:rgba(255,255,255,.3);cursor:pointer}.creation-tools button.active,.creation-tools button:hover{background:rgba(255,255,255,.055);color:var(--mint)}
.thought-flow.layer-switching{pointer-events:none}
.thought-step{position:relative;width:286px;border:1px solid rgba(255,255,255,.075);border-radius:10px;background:rgba(17,17,17,.92);box-shadow:0 16px 42px rgba(0,0,0,.26);cursor:grab;touch-action:none;user-select:none}.thought-step.active{border-color:rgba(255,255,255,.45);box-shadow:0 16px 46px rgba(0,0,0,.36),0 0 0 1px rgba(255,255,255,.08)}.thought-step:active{cursor:grabbing}.step-media{position:relative;height:164px;overflow:hidden;border-radius:9px;background:#070707}.step-media img,.step-media video{width:100%;height:100%;object-fit:cover;pointer-events:none}.media-kind{position:absolute;left:8px;top:8px;padding:3px 6px;display:flex;align-items:center;gap:4px;border-radius:5px;background:rgba(7,7,7,.68);color:rgba(255,255,255,.65);font-size:10px}.media-kind svg{width:10px}.step-media>b{position:absolute;right:8px;top:8px;font-size:10px}.history-entry{position:absolute;right:8px;bottom:8px;height:25px;padding:0 7px;border:1px solid rgba(255,255,255,.09);border-radius:6px;background:rgba(7,7,7,.7);color:rgba(255,255,255,.52);font-size:9px;cursor:pointer}.history-entry:hover{color:var(--mint)}.step-tools{position:absolute;z-index:3;right:4px;top:-32px;display:flex;gap:2px;opacity:0}.thought-step:hover .step-tools,.thought-step.active .step-tools{opacity:1}.step-tools button{width:28px;height:28px;padding:7px;border:0;border-radius:6px;background:rgba(17,17,17,.9);color:rgba(255,255,255,.5);cursor:pointer}.step-detail{position:absolute;top:168px;left:4px;display:flex;gap:4px}.step-detail span{padding:3px 6px;border-radius:5px;background:rgba(17,17,17,.72);color:rgba(255,255,255,.35);font-size:9px}.canvas-tools{position:absolute;z-index:6;left:14px;bottom:16px;padding:3px;display:flex;align-items:center;border-radius:7px;background:rgba(17,17,17,.62)}.canvas-tools span{width:40px;text-align:center;color:rgba(255,255,255,.3);font-size:10px}
.asset-panel{position:absolute;z-index:20;top:68px;right:10px;bottom:10px;width:238px;padding:13px;display:flex;flex-direction:column;border:1px solid rgba(255,255,255,.065);border-radius:8px;background:rgba(17,17,17,.92);box-shadow:-18px 0 55px rgba(0,0,0,.22);backdrop-filter:blur(22px)}.asset-panel.collapsed{top:72px;bottom:auto;width:34px;height:34px;padding:0}.asset-rail{width:34px;height:34px;padding:9px;border:0;border-radius:8px;background:rgba(17,17,17,.82);color:rgba(255,255,255,.38);cursor:pointer}.asset-panel header{height:26px;display:flex;align-items:center;justify-content:space-between}.asset-panel header div{display:flex;gap:6px}.asset-panel header strong{font-size:12px}.asset-panel header span{color:rgba(255,255,255,.28);font-size:10px}.asset-panel header button{width:28px;height:28px;padding:7px;border:0;background:transparent;color:rgba(255,255,255,.3);cursor:pointer;transform:rotate(-90deg)}.asset-search{height:30px;margin-top:8px;padding:0 8px;display:flex;align-items:center;gap:6px;border-radius:6px;background:rgba(255,255,255,.025)}.asset-search svg{width:11px}.asset-search input{width:100%;border:0;outline:0;background:transparent;color:#fff;font-size:10px}.asset-panel nav{height:35px;display:flex;align-items:end;gap:14px}.asset-panel nav button,.upload{border:0;background:transparent;color:rgba(255,255,255,.35);font-size:10px;cursor:pointer}.asset-panel nav button.active{color:#fff}.asset-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;overflow:auto}.asset-grid>button{position:relative;aspect-ratio:.95;overflow:hidden;border:0;border-radius:6px;background:#0b0b0b;cursor:pointer}.asset-grid img,.asset-grid video{width:100%;height:calc(100% - 20px);object-fit:cover}.asset-grid small{position:absolute;left:6px;right:6px;bottom:5px;overflow:hidden;color:rgba(255,255,255,.5);font-size:10px;text-align:left;text-overflow:ellipsis;white-space:nowrap}.asset-grid span{position:absolute;left:5px;right:5px;bottom:25px;height:23px;display:flex;align-items:center;justify-content:center;gap:3px;border-radius:5px;background:rgba(9,9,9,.74);color:#fff;font-size:9px;opacity:0}.asset-grid button:hover span{opacity:1}.upload{height:30px;margin-top:auto}.mobile-assets{display:none}
.control-dock{position:absolute;z-index:25;left:50%;bottom:max(28px,calc(16px + env(safe-area-inset-bottom)));width:min(680px,calc(100vw - 32px));padding:12px 20px 16px;display:grid;grid-template-rows:22px 60px 54px 34px 34px;gap:7px;border:1px solid rgba(255,255,255,.055);border-radius:14px;background:var(--surface);box-shadow:0 22px 66px rgba(0,0,0,.46);transform:translateX(-50%)}.dock-context{display:flex;align-items:center;gap:7px;min-width:0}.dock-context span{color:var(--mint);font-size:9px}.dock-context strong{overflow:hidden;font-size:10px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}.dock-context button{margin-left:auto;border:0;background:transparent;color:rgba(255,255,255,.35);font-size:9px;cursor:pointer}.reference-bar{position:relative;min-width:0;display:flex;align-items:center;gap:16px;border-bottom:1px solid var(--line)}.reference-rail{position:relative;min-width:0;flex:1;height:46px}.reference-list{height:46px;padding-right:45px;display:flex;align-items:center;gap:7px;overflow-x:auto;scrollbar-width:none}.reference-item,.reference-add{position:relative;flex:0 0 40px;width:40px;height:40px;overflow:hidden;border:0;border-radius:10px;background:rgba(255,255,255,.035);color:#fff;cursor:pointer}.reference-item img,.reference-item video{width:100%;height:100%;object-fit:cover}.reference-item span,.reference-item i{position:absolute;left:3px;padding:2px 4px;border-radius:4px;background:rgba(7,7,7,.75);font-size:8px;font-style:normal}.reference-item span{bottom:3px}.reference-item i{top:3px;color:#ffd4c8}.reference-item b{position:absolute;right:2px;top:2px;width:16px;height:16px;padding:4px;border-radius:50%;background:rgba(0,0,0,.7);opacity:0}.reference-item:hover b{opacity:1}.reference-item.invalid{opacity:.38}.reference-add{display:grid;place-items:center;border:1px dashed rgba(255,255,255,.16);color:rgba(255,255,255,.45)}.rail-fade{position:absolute;right:32px;top:0;width:35px;height:46px;pointer-events:none;background:linear-gradient(90deg,transparent,var(--surface))}.reference-count{position:absolute;right:0;top:50%;background:var(--surface);color:rgba(255,255,255,.38);font-size:9px;transform:translateY(-50%)}.reference-count.over{color:#ffc1b3}.mode-switch{flex:0 0 auto;padding:3px;display:flex;border-radius:9px;background:rgba(255,255,255,.035)}.mode-switch button{height:28px;padding:0 10px;border:0;border-radius:7px;background:transparent;color:rgba(255,255,255,.34);font-size:10px;cursor:pointer}.mode-switch button.active{background:rgba(255,255,255,.11);color:#f2f2f2}.composer-input textarea{width:100%;height:100%;padding:0;resize:none;border:0;outline:0;background:transparent;color:#fff;font-size:14px;line-height:1.55}.composer-input textarea::placeholder{color:rgba(255,255,255,.2)}.composer-meta{display:flex;align-items:center;gap:11px;padding-top:5px;border-top:1px solid var(--line)}.composer-meta select,.composer-meta button{border:0;outline:0;background:transparent;color:rgba(255,255,255,.38);font-size:10px;cursor:pointer}.composer-footer{display:flex;align-items:center}.generation-hint{color:#ffc1b3;font-size:10px}.footer-actions{margin-left:auto;display:flex;gap:7px}.generate{height:30px;padding:0 9px;display:flex;align-items:center;gap:5px;border:0;border-radius:9px;background:rgba(255,255,255,.09);color:#f2f2f2;cursor:pointer}.generate svg{width:10px}.generate span,.generate small{font-size:10px}.generate small{color:rgba(255,255,255,.32)}.generate:disabled{opacity:.35}.collapse{width:28px;height:28px;padding:7px;border:0;border-radius:8px;background:transparent;color:rgba(255,255,255,.3);cursor:pointer}.control-dock.collapsed{width:min(520px,calc(100vw - 32px));height:46px;padding:7px 8px;display:block}.dock-restore{width:100%;height:32px;display:grid;grid-template-columns:auto auto minmax(0,1fr) 15px;align-items:center;gap:8px;border:0;background:transparent;color:#fff;text-align:left}.restore-mode{padding:4px 6px;border-radius:5px;background:rgba(255,255,255,.06);color:var(--mint);font-size:9px}.restore-thumb{width:26px;height:26px;overflow:hidden;border-radius:5px}.restore-thumb img,.restore-thumb video{width:100%;height:100%;object-fit:cover}.restore-copy{min-width:0;display:flex;flex-direction:column}.restore-copy strong,.restore-copy small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.restore-copy strong{font-size:10px}.restore-copy small{color:rgba(255,255,255,.25);font-size:9px}.advanced-popover{position:absolute;z-index:8;left:0;right:0;bottom:calc(100% + 8px);padding:12px;border-radius:12px;background:rgba(17,17,17,.98);box-shadow:0 20px 55px rgba(0,0,0,.42)}.advanced-popover header{display:flex;justify-content:space-between}.advanced-popover header button{width:28px;height:28px;padding:7px;border:0;background:transparent;color:#888}.advanced-grid{display:grid;grid-template-columns:110px 1fr 1fr 105px;gap:10px}.advanced-grid label{display:flex;flex-direction:column;gap:5px;color:rgba(255,255,255,.36);font-size:10px}.advanced-grid select,.advanced-grid input[type=number],.negative-field input{height:28px;padding:0 7px;border:0;border-radius:5px;background:rgba(255,255,255,.035);color:#ccc}.range-field span{display:flex;justify-content:space-between}.negative-field{grid-column:1/-1}.reference-picker{position:absolute;z-index:12;left:0;top:50px;width:min(440px,calc(100vw - 72px));max-height:280px;padding:11px;overflow:auto;border:1px solid var(--line);border-radius:8px;background:#141414}.reference-picker>strong{font-size:11px}.reference-picker>div{margin-top:8px;display:flex;flex-wrap:wrap;gap:5px}.reference-picker>div>span{width:100%;color:#777;font-size:9px}.reference-picker button,.reference-upload{padding:5px 7px;border:0;border-radius:5px;background:rgba(255,255,255,.04);color:#aaa;font-size:9px;cursor:pointer}.reference-upload{margin-top:8px;display:flex;gap:5px}.reference-upload input{display:none}
.modal-layer{position:absolute;z-index:60;inset:0;display:grid;place-items:center;padding:24px;background:rgba(5,5,5,.72);backdrop-filter:blur(10px)}.decision-window,.history-window{width:min(980px,calc(100vw - 48px));max-height:calc(100vh - 48px);display:flex;flex-direction:column;overflow:hidden;border:1px solid rgba(255,255,255,.12);border-radius:16px;background:#141414;box-shadow:0 30px 100px rgba(0,0,0,.65)}.decision-window>header,.history-window>header{height:66px;padding:0 20px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line)}.decision-window h2,.history-window h2{margin:2px 0 0;font-size:15px}.decision-window header small,.history-window header small{color:var(--mint);font-size:9px}.decision-window>header button,.history-window>header button{width:32px;height:32px;padding:8px;border:0;background:transparent;color:#777;cursor:pointer}.decision-stage{position:relative;height:min(520px,60vh);min-height:390px}.decision-stage>svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.decision-stage>svg path{fill:none;stroke:rgba(255,255,255,.24);stroke-width:2}.decision-source{position:absolute;left:5%;top:50%;width:25%;display:flex;flex-direction:column;gap:6px;transform:translateY(-50%)}.decision-source>div{aspect-ratio:1.2;overflow:hidden;border:1px solid rgba(255,255,255,.18);border-radius:10px;background:#0b0b0b}.decision-source img,.decision-source video,.candidate-grid img,.candidate-grid video{width:100%;height:100%;object-fit:cover}.decision-source small{color:var(--mint);font-size:9px}.decision-source strong{font-size:11px}.candidate-grid{position:absolute;left:48%;right:5%;top:8%;bottom:8%;display:grid;grid-template-columns:1fr 1fr;gap:12px}.candidate-grid.count-1{left:58%;top:20%;bottom:20%;grid-template-columns:1fr}.candidate-grid.count-2{left:58%;grid-template-columns:1fr}.candidate-grid button,.history-batches section>div button{position:relative;min-height:0;overflow:hidden;border:1px solid rgba(255,255,255,.08);border-radius:10px;background:#0b0b0b;color:#fff;cursor:pointer}.candidate-grid button.selected,.history-batches button.selected{border-color:var(--mint);box-shadow:0 0 0 2px rgba(255,255,255,.12)}.candidate-grid button.generating{opacity:.58;cursor:wait}.candidate-grid button>span{position:absolute;inset:0;display:grid;place-items:center;background:rgba(5,5,5,.58);font-size:10px}.candidate-grid button>strong,.history-batches button>strong{position:absolute;left:7px;bottom:6px;padding:3px 5px;border-radius:4px;background:rgba(5,5,5,.68);font-size:9px}.decision-window>footer,.history-window>footer{height:62px;padding:0 20px;display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line)}.decision-window>footer>span,.history-window>footer>span{color:#666;font-size:9px}.decision-window>footer div,.history-window>footer div{display:flex;gap:8px}.primary,.secondary{height:32px;padding:0 12px;border-radius:8px;font-size:10px;cursor:pointer}.primary{border:0;background:rgba(255,255,255,.14);color:#f2f2f2}.secondary{border:1px solid var(--line);background:transparent;color:#aaa}.primary:disabled,.secondary:disabled{opacity:.35}.history-batches{padding:15px 20px;overflow:auto}.history-batches>section{margin-bottom:18px}.history-batches section>header{height:24px;display:flex;gap:7px;color:#aaa;font-size:10px}.history-batches section>header small{color:#555}.history-batches section>div{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.history-batches section>div button{aspect-ratio:1.35}.history-batches button.adopted::after{content:'已采用';position:absolute;right:6px;top:6px;padding:3px 5px;border-radius:4px;background:rgba(255,255,255,.14);color:var(--mint);font-size:8px}.history-batches button>span{position:absolute;right:6px;top:6px;padding:3px 5px;border-radius:4px;background:rgba(255,255,255,.14);color:var(--mint);font-size:8px}
@media(max-width:820px){.advanced-grid{grid-template-columns:1fr 1fr}.negative-field{grid-column:1/-1}.asset-panel{display:none}.mobile-assets{position:absolute;z-index:22;right:12px;top:68px;width:40px;height:40px;padding:11px;display:block;border:0;border-radius:9px;background:#141414;color:#777}.asset-panel.mobile-open{display:flex;z-index:55}.decision-window,.history-window{width:calc(100vw - 24px)}.decision-stage{min-height:440px}.decision-stage>svg{display:none}.decision-source{left:4%;right:4%;top:5%;width:auto;transform:none;display:grid;grid-template-columns:92px 1fr;align-items:center}.decision-source>div{grid-row:1/3;width:92px}.candidate-grid,.candidate-grid.count-1,.candidate-grid.count-2{left:4%;right:4%;top:34%;bottom:4%;grid-template-columns:1fr 1fr}.candidate-grid.count-1{left:25%;right:25%}.history-batches section>div{grid-template-columns:repeat(2,1fr)}}
@media(max-width:520px){.production-board{height:calc(100vh - 56px)}.board-head{height:50px}.canvas{inset:50px 0 0}.board-identity span,.saved,.head-actions button:not(.export){display:none}.control-dock{bottom:max(10px,env(safe-area-inset-bottom));width:calc(100vw - 20px);padding:10px 14px 14px;grid-template-rows:20px 56px 58px 34px 42px;gap:6px}.dock-context strong{font-size:9px}.composer-meta label:nth-of-type(2){display:none}.generate{height:38px}.generate small{display:none}.modal-layer{padding:8px}.decision-window,.history-window{width:100%;max-height:100%;border-radius:12px}.decision-window>footer,.history-window>footer{height:auto;min-height:72px;align-items:flex-start;gap:8px;padding:10px 12px;flex-direction:column}.decision-window>footer div,.history-window>footer div{width:100%}.decision-window>footer button,.history-window>footer button{flex:1}.decision-stage{height:560px}.candidate-grid,.candidate-grid.count-2{grid-template-columns:1fr 1fr}.candidate-grid.count-1{left:18%;right:18%}.history-batches{padding:12px}.history-batches section>div{grid-template-columns:1fr 1fr}.advanced-grid{grid-template-columns:1fr}.negative-field{grid-column:auto}.step-detail{display:none}}
@media(pointer:coarse){.creation-tools button,.canvas-tools button,.collapse,.mode-switch button{min-width:44px;min-height:44px}.reference-item,.reference-add{flex-basis:44px;width:44px;height:44px}.control-dock{grid-template-rows:22px 64px 64px 44px 48px}.generate{height:44px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
.control-dock{grid-template-rows:22px 60px 54px 40px;border-radius:20px}.composer-bottom{min-width:0;display:flex;align-items:center;gap:12px;border-top:1px solid var(--line)}.composer-meta{min-width:0;flex:1;padding-top:0;border-top:0}.composer-footer{flex:0 0 auto}.control-dock.collapsed{width:min(680px,calc(100vw - 32px));border-radius:20px}
@media(max-width:520px){.control-dock{grid-template-rows:20px 56px 58px 42px}.control-dock.collapsed{width:calc(100vw - 20px)}.composer-bottom{gap:4px}.composer-meta{gap:4px}.composer-meta select,.composer-meta button{font-size:9px}.generate{height:34px;padding:0 6px}.footer-actions{gap:2px}.collapse{width:26px}}
@media(pointer:coarse){.control-dock{grid-template-rows:22px 64px 64px 48px}}
.control-dock:not(.group-mode):not(.collapsed){padding:8px 10px 11px;grid-template-rows:46px 48px 42px;gap:6px}
.composer-meta label,.composer-meta button{height:28px;display:flex;align-items:center;box-sizing:border-box}.composer-meta select{height:28px;box-sizing:border-box;line-height:28px}.footer-actions{align-items:center}
.control-dock:not(.group-mode):not(.collapsed) .reference-rail,.control-dock:not(.group-mode):not(.collapsed) .reference-list{height:40px}.control-dock:not(.group-mode):not(.collapsed) .reference-item,.control-dock:not(.group-mode):not(.collapsed) .reference-add{flex-basis:34px;width:34px;height:34px;border-radius:9px}.control-dock:not(.group-mode):not(.collapsed) .rail-fade{height:40px}
.reference-add{border:1px solid rgba(255,255,255,.14);background:linear-gradient(145deg,rgba(255,255,255,.11),rgba(255,255,255,.025));box-shadow:inset 0 1px rgba(255,255,255,.045);transition:border-color .18s ease,background .18s ease,transform .18s ease}.reference-add:hover{border-color:rgba(255,255,255,.34);background:linear-gradient(145deg,rgba(255,255,255,.18),rgba(255,255,255,.05));transform:translateY(-1px)}.reference-add>svg:first-child{width:17px;color:rgba(255,255,255,.7)}.reference-add>svg:last-child{position:absolute;right:5px;bottom:5px;width:9px;padding:1px;border-radius:50%;background:var(--mint);color:#0b0b0b;box-shadow:0 0 0 2px var(--surface)}
@media(max-width:520px){.control-dock:not(.group-mode):not(.collapsed){padding:6px 8px 8px;grid-template-rows:44px 50px 38px}}
@media(pointer:coarse){.control-dock:not(.group-mode):not(.collapsed){grid-template-rows:64px 64px 48px}}
.board-breadcrumb{display:flex;align-items:center;gap:5px}.board-breadcrumb button{padding:0;border:0;background:transparent;color:var(--mint);font-size:10px;cursor:pointer}.board-breadcrumb i{color:rgba(255,255,255,.16);font-style:normal}.creation-tools button:disabled{opacity:.2;cursor:not-allowed}.step-tools button.active{color:var(--mint);background:rgba(255,255,255,.1)}.restore-thumb>svg{width:14px;height:14px;margin:6px;color:rgba(255,255,255,.35)}.thought-flow :deep(.vue-flow__node-group){width:286px;border:0;background:transparent}.thought-flow :deep(.vue-flow__nodesselection-rect),.thought-flow :deep(.vue-flow__selection){border:1px solid rgba(255,255,255,.38);background:rgba(255,255,255,.055)}
.thought-flow :deep(.vue-flow__node-group-input),.thought-flow :deep(.vue-flow__node-group-output){width:190px;border:0;background:transparent}.group-port{min-height:72px;box-sizing:border-box;padding:12px 14px;border:1px solid rgba(255,255,255,.22);border-radius:12px;background:rgba(18,23,31,.94);display:flex;flex-direction:column;gap:3px;cursor:pointer}.group-port small{font-size:9px;letter-spacing:.12em;color:rgba(255,255,255,.48)}.group-port strong{font-size:13px}.group-port span{font-size:10px;color:rgba(255,255,255,.55)}.input-port{border-color:rgba(111,205,255,.58)}.output-port{border-color:rgba(115,239,181,.64)}
.group-port-toolbar{position:absolute;top:18px;left:50%;z-index:12;display:flex;gap:6px;transform:translateX(-50%)}.group-port-toolbar button{display:flex;align-items:center;gap:4px;padding:7px 10px;border:1px solid rgba(255,255,255,.18);border-radius:8px;background:rgba(20,25,34,.92);color:#fff;font-size:11px;cursor:pointer}.group-port-toolbar button:disabled{opacity:.38;cursor:not-allowed}.group-port-toolbar svg{width:13px;height:13px}
.layer-panel{top:auto;right:auto;bottom:205px;left:16px;max-height:calc(100vh - 292px);overflow:auto}.layer-panel.floating{position:fixed;right:auto;bottom:auto}.layer-panel>header{position:sticky;top:-9px;z-index:2;margin:-9px -9px 0;padding:11px 12px 8px;background:rgba(15,15,15,.96);cursor:grab}.layer-panel>header:active{cursor:grabbing}
.group-notice{position:absolute;z-index:8;left:50%;top:16px;padding:7px 10px;border:1px solid rgba(255,193,179,.16);border-radius:8px;background:rgba(33,24,24,.92);color:#ffc1b3;font-size:9px;transform:translateX(-50%)}
.group-node{position:relative;width:286px;height:164px;overflow:hidden;border:1px solid rgba(255,255,255,.16);border-radius:14px;background:#111111;box-shadow:0 18px 46px rgba(0,0,0,.32);cursor:grab;user-select:none}.group-node.active{border-color:rgba(255,255,255,.82);outline:2px solid rgba(255,255,255,.5);outline-offset:4px;box-shadow:0 20px 52px rgba(0,0,0,.42),0 0 22px rgba(255,255,255,.16)}.group-cover{position:absolute;inset:0;background:#090909}.group-cover>img,.group-cover>video{width:100%;height:100%;object-fit:cover;opacity:.48}.group-cover>span{height:100%;display:grid;place-items:center;gap:5px;color:rgba(255,255,255,.3);font-size:10px}.group-cover>span svg{width:24px}.group-node>header{position:absolute;inset:0 0 auto;padding:10px 11px;display:flex;align-items:flex-start;justify-content:space-between;background:linear-gradient(180deg,rgba(6,6,6,.88),transparent)}.group-node>header>div{min-width:0;display:flex;align-items:center;gap:6px}.group-node>header svg{flex:0 0 13px;width:13px;color:var(--mint)}.group-node>header strong{overflow:hidden;font-size:11px;font-weight:540;text-overflow:ellipsis;white-space:nowrap}.group-node>header small{flex:0 0 auto;color:rgba(255,255,255,.42);font-size:8px}.group-output-strip{position:absolute;left:8px;right:8px;bottom:8px;height:36px;padding:4px;display:flex;align-items:center;gap:5px;border-radius:9px;background:rgba(7,7,7,.78);backdrop-filter:blur(12px)}.group-output-strip button{width:28px;height:28px;padding:0;overflow:hidden;border:1px solid transparent;border-radius:6px;background:#161616;color:#888}.group-output-strip button.active{border-color:var(--mint)}.group-output-strip img,.group-output-strip video{width:100%;height:100%;object-fit:cover}.group-output-strip>span{color:rgba(255,255,255,.45);font-size:9px}.group-output-strip .group-enter{margin-left:auto;padding:7px;background:transparent;cursor:pointer}.group-output-strip .group-enter svg{width:13px}
.control-dock.group-mode:not(.collapsed){grid-template-rows:28px 92px 40px}.group-context input{min-width:0;width:180px;border:0;border-bottom:1px solid rgba(255,255,255,.08);outline:0;background:transparent;color:#fff;font-size:12px}.group-context small{margin-left:auto;color:rgba(255,255,255,.32);font-size:9px}.group-output-manager{display:flex;align-items:center;gap:8px;overflow-x:auto;scrollbar-width:none}.group-output-item{position:relative;flex:0 0 112px;height:76px;padding:5px;display:grid;grid-template-columns:40px 1fr;grid-template-rows:1fr 20px;gap:4px;border:1px solid rgba(255,255,255,.07);border-radius:10px;background:rgba(255,255,255,.025);color:#aaa;text-align:left;cursor:pointer}.group-output-item.active{border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.045)}.group-output-item>i{grid-row:1/3;width:40px;overflow:hidden;border-radius:7px}.group-output-manager img,.group-output-manager video{width:100%;height:100%;object-fit:cover}.group-output-manager input{min-width:0;width:100%;border:0;outline:0;background:transparent;color:#ddd;font-size:9px}.group-output-item>span{display:flex;gap:3px}.group-output-item>span button{width:18px;height:18px;padding:0;display:grid;place-items:center;border:0;border-radius:4px;background:rgba(255,255,255,.04);color:#aaa;font-size:9px;cursor:pointer}.group-output-empty{width:100%;height:72px;display:grid;place-items:center;border:1px dashed rgba(255,255,255,.1);border-radius:10px;color:rgba(255,255,255,.28);font-size:10px}.group-panel-actions{display:flex;align-items:center;gap:7px;border-top:1px solid var(--line)}.group-panel-actions>span{min-width:0;flex:1;overflow:hidden;color:#ffc1b3;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.group-panel-actions button{display:flex;align-items:center;gap:5px}.group-panel-actions button svg{width:11px}.group-panel-actions .danger{color:#d99086}.group-panel-actions .collapse{padding:7px}
@media(max-width:520px){.control-dock.group-mode:not(.collapsed){grid-template-rows:24px 82px 38px}.group-context input{width:120px}.group-output-item{flex-basis:104px;height:68px}.group-panel-actions .secondary:first-of-type{display:none}.group-panel-actions>span{display:none}.group-panel-actions button{padding:0 7px}}
.production-board{height:calc(100vh - 22px);height:calc(100dvh - 22px)}
.control-dock{bottom:28px;bottom:max(28px,calc(16px + env(safe-area-inset-bottom)));width:calc(100vw - 32px);max-width:680px;will-change:transform}
.board-head{-webkit-backdrop-filter:blur(18px)}.asset-panel{-webkit-backdrop-filter:blur(22px)}.modal-layer{-webkit-backdrop-filter:blur(10px)}.group-output-strip{-webkit-backdrop-filter:blur(12px)}
.reference-list,.asset-grid,.group-output-manager,.history-batches{-webkit-overflow-scrolling:touch}
@media(max-width:520px){.production-board{height:calc(100vh - 56px);height:calc(100dvh - 56px)}.control-dock{bottom:10px;bottom:max(10px,env(safe-area-inset-bottom));width:calc(100vw - 20px)}.decision-window,.history-window{max-height:calc(100vh - 16px);max-height:calc(100dvh - 16px)}}
.asset-panel{top:56px;right:0;bottom:0;width:292px;border-radius:12px 0 0;box-shadow:-8px 0 24px rgba(0,0,0,.12);transition:top .2s ease,right .2s ease,bottom .2s ease,border-radius .2s ease,box-shadow .2s ease}.asset-panel.floating{top:74px;right:16px;bottom:16px;border-radius:14px;box-shadow:0 14px 34px rgba(0,0,0,.18)}.asset-panel.collapsed{right:10px;top:72px;bottom:auto;width:34px;border-radius:8px}.asset-actions{display:flex;align-items:center;gap:0}.asset-actions button:first-child{transform:none}.asset-actions button:first-child:hover,.asset-actions button:first-child:focus-visible{color:var(--mint)}
@media(max-width:820px){.asset-panel,.asset-panel.floating{top:68px;right:10px;bottom:10px;width:min(292px,calc(100vw - 20px));border-radius:12px}.asset-panel.collapsed{top:72px;right:10px;bottom:auto;width:34px}}

/* Cinema workbench visual layer */
.production-board{
  --canvas:#090909;--surface-1:#101010;--surface-2:#151515;--surface-3:#1b1b1b;
  --border-soft:rgba(255,255,255,.055);--border-mid:rgba(255,255,255,.12);--border-strong:rgba(255,255,255,.42);
  --text-1:rgba(255,255,255,.92);--text-2:rgba(255,255,255,.58);--text-3:rgba(255,255,255,.32);
  --shadow-card:0 14px 34px rgba(0,0,0,.22);--shadow-float:0 18px 48px rgba(0,0,0,.24);
  --ease:cubic-bezier(.2,.72,.2,1);--surface:rgba(16,16,16,.97);--line:var(--border-soft);
  font-family:Inter,-apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Microsoft YaHei",sans-serif;
  background:var(--canvas);color:var(--text-1);
}
.board-head{height:52px;padding:0 20px;border-bottom:1px solid rgba(255,255,255,.035);background:linear-gradient(180deg,rgba(15,15,15,.94),rgba(10,10,10,.84));box-shadow:none}
.board-identity{gap:12px}.board-identity span{font-size:11px;color:var(--text-3)}.board-identity h1{font-size:16px;font-weight:620;letter-spacing:-.015em}.head-actions{gap:10px}.head-actions button{font-size:11px;color:var(--text-2);transition:color .18s var(--ease),background .18s var(--ease)}.head-actions button:hover{color:var(--text-1)}.head-actions .export{height:32px;padding:0 13px;border:1px solid var(--border-mid);border-radius:9px;background:rgba(255,255,255,.08);color:var(--text-1)}.head-actions .export:hover{background:rgba(255,255,255,.13)}.saved{font-size:10px;color:var(--text-3)}.saved i{background:#8a8a8a}
.canvas{inset:52px 0 0;background:var(--canvas)}.canvas::after{content:"";position:absolute;z-index:2;inset:0;pointer-events:none;box-shadow:inset 0 0 180px rgba(0,0,0,.44)}
.thought-flow{background-color:var(--canvas);background-image:radial-gradient(circle at 48% 42%,rgba(255,255,255,.028),transparent 38%),radial-gradient(rgba(255,255,255,.075) .55px,transparent .65px);background-size:100% 100%,24px 24px}
.thought-flow :deep(.vue-flow__pane){cursor:crosshair}.thought-flow :deep(.vue-flow__pane.dragging){cursor:grabbing}
.thought-trail{opacity:.7;transition:opacity .18s var(--ease)}.thought-trail.active{opacity:1}.trajectory-shadow{stroke:#050505;stroke-width:4.5;stroke-opacity:.82}.trajectory-stroke{stroke-width:1.9}.thought-trail.active .trajectory-stroke{filter:drop-shadow(0 0 4px rgba(255,255,255,.32))}
.thought-step{border-color:var(--border-soft);border-radius:12px;background:var(--surface-1);box-shadow:var(--shadow-card);transition:border-color .18s var(--ease),box-shadow .18s var(--ease),transform .18s var(--ease)}.thought-step:hover{border-color:var(--border-mid);box-shadow:0 18px 40px rgba(0,0,0,.28);transform:translateY(-1px)}.thought-step.active{border-color:rgba(255,255,255,.82);box-shadow:0 20px 48px rgba(0,0,0,.42),0 0 0 2px rgba(255,255,255,.5),0 0 0 6px rgba(255,255,255,.08),0 0 22px rgba(255,255,255,.16)}
.step-media{height:164px;border-radius:11px;background:#080808}.step-media::after{content:"";position:absolute;z-index:1;inset:0;pointer-events:none;background:linear-gradient(180deg,rgba(0,0,0,.12),transparent 38%,rgba(0,0,0,.22))}.step-media img,.step-media video{position:relative;z-index:1}.media-kind,.history-entry,.step-media>b{z-index:3;border:1px solid rgba(255,255,255,.09);border-radius:7px;background:rgba(7,7,7,.68);color:rgba(255,255,255,.68);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}.media-kind{left:9px;top:9px;padding:4px 7px;font-size:10px}.step-media>b{right:9px;top:9px;padding:4px 7px;font-size:9px}.history-entry{right:9px;bottom:9px;height:26px;padding:0 8px;font-size:9px}.history-entry:hover{border-color:rgba(255,255,255,.2);color:#fff}
.step-tools{right:7px;top:7px;padding:3px;gap:2px;border:1px solid rgba(255,255,255,.08);border-radius:9px;background:rgba(12,12,12,.78);opacity:0;transform:translateY(-3px);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);transition:opacity .16s var(--ease),transform .16s var(--ease)}.thought-step:hover .step-tools,.thought-step.active .step-tools{opacity:1;transform:none}.step-tools button{width:26px;height:26px;padding:7px;border-radius:6px;background:transparent;color:var(--text-2)}.step-tools button:hover,.step-tools button.active{background:rgba(255,255,255,.09);color:#fff}.step-detail{top:170px;left:6px}.step-detail span{border:1px solid rgba(255,255,255,.05);background:rgba(13,13,13,.82);color:var(--text-3);font-size:9px}
.video-monitor{position:absolute;z-index:0;inset:0;display:grid;place-content:center;justify-items:center;gap:8px;background:repeating-linear-gradient(0deg,transparent 0 15px,rgba(255,255,255,.018) 16px),radial-gradient(circle at center,rgba(255,255,255,.045),transparent 44%),#080808;color:rgba(255,255,255,.24);transition:opacity .2s var(--ease)}.video-monitor::before,.video-monitor::after{content:"";position:absolute;left:8%;right:8%;top:50%;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.055),transparent)}.video-monitor::after{left:50%;top:8%;bottom:8%;width:1px;height:auto}.video-monitor svg{width:22px}.video-monitor em{font-size:8px;font-style:normal;letter-spacing:.16em}.step-media>video[data-ready="true"]+.video-monitor{opacity:0}
.creation-tools,.canvas-tools{border:1px solid var(--border-soft);border-radius:10px;background:rgba(16,16,16,.8);box-shadow:0 10px 24px rgba(0,0,0,.16);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}.creation-tools{left:16px;top:16px;padding:4px;gap:3px}.creation-tools button,.canvas-tools button{width:32px;height:32px;padding:8px;border-radius:7px;color:var(--text-3);transition:color .16s var(--ease),background .16s var(--ease)}.creation-tools button.active,.creation-tools button:hover,.canvas-tools button:hover{background:rgba(255,255,255,.075);color:var(--text-1)}.canvas-tools{left:16px;bottom:18px;padding:4px}.canvas-tools span{font-size:10px;color:var(--text-3)}
.asset-panel{padding:16px;border-color:var(--border-soft);border-radius:14px 0 0 14px;background:rgba(16,16,16,.96);box-shadow:-8px 0 24px rgba(0,0,0,.1)}.asset-panel.floating{border-radius:16px;box-shadow:var(--shadow-float)}.asset-panel header{height:34px}.asset-panel header strong{font-size:13px;font-weight:620}.asset-panel header span{font-size:10px;color:var(--text-3)}.asset-panel header button{border-radius:7px;color:var(--text-3);transition:color .16s var(--ease),background .16s var(--ease)}.asset-panel header button:hover{background:rgba(255,255,255,.06);color:var(--text-1)}.asset-search{height:34px;margin-top:10px;padding:0 10px;border:1px solid rgba(255,255,255,.035);border-radius:8px;background:rgba(255,255,255,.035)}.asset-search svg{width:12px;color:var(--text-3)}.asset-search input{font-size:11px;color:var(--text-1)}.asset-panel nav{height:42px;gap:16px}.asset-panel nav button,.upload{font-size:11px}.asset-panel nav button{position:relative;padding:0 0 8px;color:var(--text-3)}.asset-panel nav button.active{color:var(--text-1)}.asset-panel nav button.active::after{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;background:rgba(255,255,255,.65)}
.asset-grid{gap:9px;padding:1px}.asset-grid>button{aspect-ratio:1.08;border:1px solid rgba(255,255,255,.045);border-radius:9px;background:#0b0b0b;box-shadow:none;transition:border-color .18s var(--ease),transform .18s var(--ease)}.asset-grid>button:hover{border-color:rgba(255,255,255,.18);transform:translateY(-1px)}.asset-grid>button::after{content:"";position:absolute;z-index:1;inset:45% 0 0;background:linear-gradient(transparent,rgba(0,0,0,.82));pointer-events:none}.asset-grid img,.asset-grid video{height:100%;transition:transform .22s var(--ease)}.asset-grid>button:hover img,.asset-grid>button:hover video{transform:scale(1.025)}.asset-grid small{z-index:2;left:8px;right:8px;bottom:7px;color:rgba(255,255,255,.76);font-size:10px}.asset-grid span{z-index:3;left:8px;right:8px;bottom:30px;height:27px;border:1px solid rgba(255,255,255,.1);border-radius:7px;background:rgba(10,10,10,.78);font-size:10px;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);transition:opacity .16s var(--ease)}.upload{height:36px;margin-top:12px;border-top:1px solid var(--border-soft);color:var(--text-2)}
.upload{display:flex;align-items:center;justify-content:center;gap:6px}
.upload svg{width:13px;height:13px;flex:0 0 13px}
.control-dock{border-color:var(--border-soft);background:rgba(16,16,16,.965);box-shadow:0 15px 42px rgba(0,0,0,.25)}.control-dock::before{content:"";position:absolute;left:20px;right:20px;top:0;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent)}.composer-input textarea{font-size:14px;font-weight:450;letter-spacing:-.005em;color:var(--text-1)}.composer-meta select,.composer-meta button{font-size:11px;color:var(--text-3);transition:color .16s var(--ease)}.composer-meta select:hover,.composer-meta button:hover{color:var(--text-1)}.mode-switch{border:1px solid rgba(255,255,255,.035);background:rgba(255,255,255,.025)}.mode-switch button{font-size:11px}.mode-switch button.active{background:rgba(255,255,255,.12);color:#fff}.generate{height:32px;border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.095);color:#fff;transition:background .16s var(--ease),border-color .16s var(--ease)}.generate:hover:not(:disabled){border-color:rgba(255,255,255,.17);background:rgba(255,255,255,.15)}.generate span,.generate small{font-size:10px}.collapse:hover{background:rgba(255,255,255,.06);color:var(--text-1)}.reference-add{border-color:rgba(255,255,255,.12);background:linear-gradient(145deg,rgba(255,255,255,.085),rgba(255,255,255,.018))}.reference-add:hover{border-color:rgba(255,255,255,.28);background:linear-gradient(145deg,rgba(255,255,255,.14),rgba(255,255,255,.04))}
.decision-window,.history-window{border-color:var(--border-mid);background:var(--surface-2);box-shadow:0 30px 80px rgba(0,0,0,.54)}.candidate-grid button,.history-batches section>div button{border-radius:12px}.candidate-grid button.selected,.history-batches button.selected{border-color:rgba(255,255,255,.62);box-shadow:0 0 0 2px rgba(255,255,255,.09)}
.candidate-grid button.failed{opacity:1;cursor:default}.candidate-grid button.failed>span{padding:16px;line-height:1.5;color:#ffb5ad;text-align:center}
.thought-step.generating{border-color:rgba(255,255,255,.24);box-shadow:0 0 0 1px rgba(255,255,255,.05),0 14px 40px rgba(0,0,0,.38)}.generation-pulse,.generation-error{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;background:radial-gradient(circle at 50% 38%,rgba(255,255,255,.11),transparent 55%),#0a0a0a}.generation-pulse::after{content:'';position:absolute;inset:0;background:linear-gradient(115deg,transparent 36%,rgba(255,255,255,.13) 50%,transparent 64%);transform:translateX(-100%);animation:generation-sweep 1.8s ease-in-out infinite}.generation-pulse i{width:30px;height:30px;border:2px solid rgba(255,255,255,.12);border-top-color:#fff;border-radius:50%;animation:generation-spin .8s linear infinite}.generation-pulse span{font-size:11px;color:#fff}.generation-pulse small{color:rgba(255,255,255,.4);font-size:9px}.generation-error{padding:20px;background:#120f0f}.generation-error strong{color:#ffc1b8;font-size:11px}.generation-error span{max-width:80%;color:rgba(255,255,255,.43);font-size:9px;line-height:1.5;text-align:center}@keyframes generation-spin{to{transform:rotate(360deg)}}@keyframes generation-sweep{to{transform:translateX(100%)}}
.layer-panel{position:absolute;z-index:24;top:68px;right:258px;width:192px;padding:9px;border:1px solid var(--border-soft);border-radius:12px;background:rgba(15,15,15,.9);box-shadow:0 14px 34px rgba(0,0,0,.28);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}.layer-panel header,.layer-panel header>div,.layer-row,.layer-effects{display:flex;align-items:center}.layer-panel header{justify-content:space-between;padding:2px 3px 8px}.layer-panel header>div{gap:6px}.layer-panel header strong{font-size:11px}.layer-panel header span,.layer-panel small{color:var(--text-3);font-size:9px}.layer-panel header button{height:24px;padding:0 7px;border:1px solid rgba(255,255,255,.1);border-radius:6px;background:rgba(255,255,255,.06);color:#fff;font-size:9px;cursor:pointer}.layer-panel header button:disabled{opacity:.35;cursor:not-allowed}.layer-panel section{padding:7px 4px;border-top:1px solid rgba(255,255,255,.055);cursor:pointer}.layer-panel section.active{margin:0 -4px;padding:7px 8px;border-radius:8px;background:rgba(255,255,255,.065)}.layer-row{gap:3px}.layer-row input{min-width:0;flex:1;border:0;outline:0;background:transparent;color:var(--text-2);font-size:10px}.layer-row button{width:20px;height:20px;padding:0;border:0;border-radius:4px;background:transparent;color:var(--text-3);font-size:10px;cursor:pointer}.layer-row button:hover:not(:disabled){background:rgba(255,255,255,.08);color:#fff}.layer-row button:disabled{opacity:.25;cursor:not-allowed}.layer-effects{display:grid;grid-template-columns:28px 1fr 28px;gap:4px;margin-top:6px;color:var(--text-3);font-size:8px}.layer-effects label{display:contents}.layer-effects input{width:100%;accent-color:#ddd}.layer-effects span{text-align:right;font-size:8px}.thought-trail.background{opacity:.32;filter:blur(.35px)}.thought-step.background,.group-node.background,.text-annotation.background,.brush-annotation.background{pointer-events:none}@media(max-width:820px){.layer-panel{right:12px;top:116px;width:174px}.asset-panel:not(.mobile-open)~.layer-panel{right:12px}}@media(max-width:520px){.layer-panel{top:62px;right:10px;width:166px}.layer-effects{grid-template-columns:26px 1fr 26px}}
.canvas{background:#0b0b0b radial-gradient(rgba(255,255,255,.08) .65px,transparent .65px);background-size:24px 24px}.thought-flow{position:relative;z-index:2;background:transparent!important}
@media(max-width:820px){.asset-panel,.asset-panel.floating{padding:14px;border-radius:14px}.board-head{padding:0 14px}.creation-tools{left:10px;top:10px}.canvas-tools{left:10px}}
@media(max-width:520px){.board-head{height:50px}.canvas{inset:50px 0 0}.composer-input textarea{font-size:13px}.asset-grid{gap:8px}.control-dock::before{left:12px;right:12px}.canvas-tools{bottom:calc(176px + env(safe-area-inset-bottom))}}
@media(prefers-reduced-motion:reduce){.thought-step,.step-tools,.asset-panel,.asset-grid>button,.asset-grid img,.asset-grid video,.reference-add,.generate{transition:none!important}.thought-step:hover,.asset-grid>button:hover,.reference-add:hover{transform:none!important}}

/* Header controls live directly on the canvas instead of occupying a bar. */
.board-head{height:48px;padding:8px 16px;align-items:flex-start;border:0;background:transparent;box-shadow:none;backdrop-filter:none;-webkit-backdrop-filter:none;pointer-events:none}
.board-identity,.head-actions{height:32px;padding:0 2px;pointer-events:auto}
.board-identity h1{text-shadow:0 1px 8px rgba(0,0,0,.72)}
.head-actions{padding-left:8px;border-radius:10px;background:rgba(10,10,10,.36);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
.snapshot-menu{position:absolute;top:38px;right:0;width:220px;padding:10px;border:1px solid var(--border-mid);border-radius:10px;background:rgba(18,18,18,.98);box-shadow:0 14px 32px rgba(0,0,0,.35)}.snapshot-menu header{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}.snapshot-menu header strong{font-size:11px}.snapshot-menu button{display:flex;width:100%;justify-content:space-between;padding:7px 4px;border-radius:5px;text-align:left}.snapshot-menu header button{width:auto;padding:4px 6px;background:rgba(255,255,255,.09);color:#fff}.snapshot-menu p{margin:8px 0;color:var(--text-3);font-size:10px}.snapshot-menu small{color:var(--text-3)}
.canvas{inset:0}
.creation-tools{top:56px}
@media(max-width:820px){.board-head{padding:8px 10px}.creation-tools{top:54px}}
@media(max-width:520px){.board-head{height:48px}.canvas{inset:0}.creation-tools{top:52px}}
.group-node.active{border-color:rgba(255,255,255,.82);outline:0;box-shadow:0 20px 52px rgba(0,0,0,.42),0 0 0 2px rgba(255,255,255,.5),0 0 0 6px rgba(255,255,255,.08),0 0 22px rgba(255,255,255,.16)}
.step-media img,.step-media video,.group-cover>img,.group-cover>video{display:block;backface-visibility:hidden;transform:translateZ(0);image-rendering:auto}
.canvas.brush-mode .thought-flow :deep(.vue-flow__pane){cursor:crosshair}.thought-flow :deep(.vue-flow__node-text-annotation),.thought-flow :deep(.vue-flow__node-brush-annotation){border:0;background:transparent}.text-annotation{width:210px;height:76px;padding:10px;border:1px solid rgba(255,255,255,.2);border-radius:10px;background:rgba(20,20,20,.9);box-shadow:0 12px 28px rgba(0,0,0,.2)}.text-annotation textarea{width:100%;height:100%;padding:0;resize:none;border:0;outline:0;background:transparent;color:rgba(255,255,255,.92);font:500 15px/1.4 inherit}.brush-annotation{width:100%;height:100%;min-width:32px;min-height:32px;border:1px solid rgba(255,255,255,.15);border-radius:12px;background:rgba(18,18,18,.55);box-shadow:0 12px 28px rgba(0,0,0,.18)}.brush-annotation svg{width:100%;height:100%;overflow:visible}.brush-annotation path{fill:none;stroke:#e8d9a6;stroke-width:5;stroke-linecap:round;stroke-linejoin:round}.thought-flow :deep(.vue-flow__node-text-annotation.selected) .text-annotation,.thought-flow :deep(.vue-flow__node-brush-annotation.selected) .brush-annotation{border-color:rgba(255,255,255,.75);box-shadow:0 0 0 2px rgba(255,255,255,.28),0 14px 32px rgba(0,0,0,.28)}
.production-board,.production-board button,.production-board img,.production-board svg{-webkit-user-select:none;user-select:none}.production-board input,.production-board textarea,.production-board select{-webkit-user-select:text;user-select:text}
.trajectory-arrow{opacity:.9;filter:drop-shadow(0 0 3px currentColor)}.thought-trail.active .trajectory-arrow{opacity:1;filter:drop-shadow(0 0 5px currentColor)}
.layer-panel{top:auto;right:auto;bottom:205px;left:16px;max-height:calc(100vh - 292px);overflow:auto}.layer-panel.floating{position:fixed;right:auto;bottom:auto}.layer-panel>header{position:sticky;top:-9px;z-index:2;margin:-9px -9px 0;padding:11px 12px 8px;background:rgba(15,15,15,.96);cursor:grab}.layer-panel>header:active{cursor:grabbing}@media(max-width:820px){.layer-panel{top:auto;right:auto;bottom:190px;left:10px;width:174px}}@media(max-width:520px){.layer-panel{top:auto;right:auto;bottom:calc(330px + env(safe-area-inset-bottom));left:10px;width:166px;max-height:34vh}}
.layer-name{min-width:0;flex:1;overflow:hidden;color:var(--text-2);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.layer-name-editor{height:22px;padding:0 5px!important;border:1px solid rgba(255,255,255,.3)!important;border-radius:5px!important;background:#101010!important;color:#fff!important}.layer-row i{width:18px;color:var(--text-3);font-size:9px;font-style:normal;text-align:center}.layer-row i.hidden{opacity:.35}.layer-row small{flex:0 0 auto;font-size:9px}.layer-context-menu{position:fixed;z-index:80;width:156px;padding:5px;border:1px solid rgba(255,255,255,.14);border-radius:9px;background:rgba(18,18,18,.98);box-shadow:0 16px 38px rgba(0,0,0,.48);backdrop-filter:blur(14px)}.layer-context-menu button{display:block;width:100%;height:30px;padding:0 9px;border:0;border-radius:6px;background:transparent;color:rgba(255,255,255,.78);font-size:11px;text-align:left;cursor:pointer}.layer-context-menu button:hover:not(:disabled){background:rgba(255,255,255,.09);color:#fff}.layer-context-menu button.danger{color:#ffaaa1}.layer-context-menu button:disabled{opacity:.3;cursor:not-allowed}
.asset-panel:not(.collapsed){width:360px;padding:0;overflow:hidden}.asset-panel.floating:not(.collapsed){top:86px;right:24px;bottom:auto;width:min(680px,calc(100vw - 48px));height:min(560px,calc(100vh - 180px));border-radius:16px}.asset-window-head{flex:0 0 58px!important;height:58px!important;padding:0 16px;border-bottom:1px solid var(--border-soft)}.asset-window-head>div:first-child{display:grid!important;grid-template-columns:auto 1fr;align-items:center;gap:1px 7px!important}.asset-window-head small{grid-column:1/-1;color:var(--text-3);font-size:9px}.asset-window-head strong{font-size:14px!important}.asset-window-head span{font-size:9px!important}.asset-window-body{min-height:0;flex:1;display:grid;grid-template-columns:112px minmax(0,1fr)}.asset-categories{padding:14px 10px;border-right:1px solid var(--border-soft);background:rgba(255,255,255,.018)}.asset-categories>strong{display:block;margin:0 7px 8px;color:var(--text-3);font-size:9px;font-weight:500}.asset-categories>button{width:100%;height:31px;padding:0 8px;display:flex;align-items:center;justify-content:space-between;border:0;border-radius:7px;background:transparent;color:var(--text-3);font-size:10px;cursor:pointer}.asset-categories>button span{font-size:9px;opacity:.55}.asset-categories>button.active,.asset-categories>button:hover{background:rgba(255,255,255,.075);color:#fff}.asset-categories>i{display:block;margin:12px 6px;border-top:1px solid var(--border-soft)}.asset-categories>small{display:block;padding:0 7px;color:rgba(255,255,255,.3);font-size:8px;line-height:1.5}.asset-browser{min-width:0;min-height:0;padding:12px;display:flex;flex-direction:column}.asset-browser-tools{display:flex;gap:8px}.asset-browser-tools .asset-search{height:32px;margin:0;flex:1}.asset-browser-tools .upload{width:68px;height:32px;margin:0;border:1px solid var(--border-soft);border-radius:8px;background:rgba(255,255,255,.05)}.asset-browser .asset-grid{min-height:0;margin-top:10px;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.asset-browser .asset-grid>button{aspect-ratio:1.2;border:1px solid rgba(255,255,255,.06);border-radius:9px}.asset-browser .asset-grid>button.selected{border-color:rgba(255,255,255,.72);box-shadow:0 0 0 2px rgba(255,255,255,.12)}.asset-browser .asset-grid>button::after{inset:55% 0 0}.asset-browser .asset-grid em{position:absolute;z-index:2;top:7px;right:7px;padding:3px 5px;border-radius:5px;background:rgba(0,0,0,.62);color:rgba(255,255,255,.6);font-size:8px;font-style:normal}.asset-empty{flex:1;display:grid;place-items:center;color:var(--text-3);font-size:11px}.asset-inspector{flex:0 0 72px;padding:10px 12px;display:grid;grid-template-columns:52px minmax(0,1fr) auto auto;align-items:center;gap:10px;border-top:1px solid var(--border-soft);background:rgba(255,255,255,.018)}.asset-preview{width:52px;height:52px;overflow:hidden;border-radius:8px;background:#080808}.asset-preview img,.asset-preview video{width:100%;height:100%;object-fit:cover}.asset-inspector>div:nth-child(2){min-width:0;display:flex;flex-direction:column;gap:3px}.asset-inspector small,.asset-inspector span{color:var(--text-3);font-size:8px}.asset-inspector strong{overflow:hidden;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.asset-inspector>button{height:30px;padding:0 10px;border-radius:7px;font-size:10px}.asset-inspector>button.primary{display:flex;align-items:center;gap:4px}.asset-inspector>button svg{width:12px}@media(max-width:820px){.asset-panel:not(.collapsed),.asset-panel.floating:not(.collapsed){top:68px;right:10px;bottom:10px;width:calc(100vw - 20px);height:auto}.asset-window-body{grid-template-columns:92px minmax(0,1fr)}.asset-browser .asset-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.asset-window-body{grid-template-columns:1fr}.asset-categories{padding:7px;display:flex;gap:4px;border-right:0;border-bottom:1px solid var(--border-soft)}.asset-categories>strong,.asset-categories>i,.asset-categories>small{display:none}.asset-categories>button{justify-content:center;gap:5px}.asset-inspector{grid-template-columns:42px minmax(0,1fr) auto}.asset-preview{width:42px;height:42px}.asset-inspector .secondary{display:none}}
.asset-window-head.draggable{cursor:grab}.asset-window-head.draggable:active{cursor:grabbing}
.production-board{--board-bottom-gap:max(18px,env(safe-area-inset-bottom))}.control-dock{bottom:var(--board-bottom-gap)}.asset-panel:not(.floating):not(.collapsed){bottom:var(--board-bottom-gap)}
.asset-categories{overflow-y:auto}.asset-categories>strong:not(:first-child){margin-top:2px}.collection-placeholder{height:100%;display:grid!important;place-items:center;background:rgba(255,255,255,.025)!important}.collection-placeholder svg{width:24px;color:rgba(255,255,255,.28)}.collection-sharing{display:flex!important;flex-direction:row!important;gap:3px!important}.collection-sharing button{height:28px;padding:0 8px;border:1px solid var(--border-soft);border-radius:6px;background:transparent;color:var(--text-3);font-size:9px;cursor:pointer}.collection-sharing button.active{border-color:rgba(255,255,255,.35);background:rgba(255,255,255,.1);color:#fff}.asset-inspector .primary:disabled{opacity:.35;cursor:not-allowed}
</style>
