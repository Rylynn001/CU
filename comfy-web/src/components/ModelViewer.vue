<script setup lang="ts">
import { ref, watch, onBeforeUnmount, toRaw } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js'
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [boolean]; 'capture': [File] }>()

// ── DOM refs ──
const mainCanvasRef = ref<HTMLCanvasElement | null>(null)
const thumbContainerRef = ref<HTMLDivElement | null>(null)

// ── 状态 ──
interface BoneEntry { name: string; bone: THREE.Bone; rx: number; ry: number; rz: number }
interface CamEntry { id: number; label: string; cam: THREE.PerspectiveCamera; helper: THREE.CameraHelper; thumbUrl: string; px: number; py: number; pz: number; rx: number; ry: number; rz: number; fov: number }
interface ModelEntry { id: number; label: string; obj: THREE.Group; px: number; py: number; pz: number; rx: number; ry: number; rz: number; bones: BoneEntry[] }

const BONE_MAP: Record<string, { label: string; axes: [string, string, string] }> = {
  Hips:          { label: '骨盆',   axes: ['前倾', '转身', '侧倾'] },
  Spine:         { label: '脊椎',   axes: ['前倾', '转身', '侧倾'] },
  Spine1:        { label: '腰部',   axes: ['前倾', '转身', '侧倾'] },
  Spine2:        { label: '躯干',   axes: ['前倾', '扭转', '侧倾'] },
  Neck:          { label: '颈部',   axes: ['点头', '转头', '歪头'] },
  Head:          { label: '头部',   axes: ['点头', '转头', '歪头'] },
  LeftShoulder:  { label: '左肩',   axes: ['前举', '扭转', '外展'] },
  LeftArm:       { label: '左上臂', axes: ['前举', '扭转', '外展'] },
  LeftForeArm:   { label: '左前臂', axes: ['弯曲', '扭转', '侧弯'] },
  LeftHand:      { label: '左手腕', axes: ['弯曲', '扭转', '偏转'] },
  RightShoulder: { label: '右肩',   axes: ['前举', '扭转', '外展'] },
  RightArm:      { label: '右上臂', axes: ['前举', '扭转', '外展'] },
  RightForeArm:  { label: '右前臂', axes: ['弯曲', '扭转', '侧弯'] },
  RightHand:     { label: '右手腕', axes: ['弯曲', '扭转', '偏转'] },
  LeftUpLeg:     { label: '左大腿', axes: ['前踢', '扭转', '外展'] },
  LeftLeg:       { label: '左小腿', axes: ['弯曲', '扭转', '侧弯'] },
  LeftFoot:      { label: '左脚踝', axes: ['背屈', '扭转', '外翻'] },
  LeftToeBase:   { label: '左脚趾', axes: ['弯曲', '扭转', '偏转'] },
  RightUpLeg:    { label: '右大腿', axes: ['前踢', '扭转', '外展'] },
  RightLeg:      { label: '右小腿', axes: ['弯曲', '扭转', '侧弯'] },
  RightFoot:     { label: '右脚踝', axes: ['背屈', '扭转', '外翻'] },
  RightToeBase:  { label: '右脚趾', axes: ['弯曲', '扭转', '偏转'] },
}

function getBoneDisplay(name: string): { label: string; axes: [string, string, string] } {
  if (BONE_MAP[name]) return BONE_MAP[name]
  for (const key of Object.keys(BONE_MAP)) {
    if (name.includes(key)) return BONE_MAP[key]
  }
  return { label: name, axes: ['X轴', 'Y轴', 'Z轴'] }
}

const cameras = ref<CamEntry[]>([])
const models = ref<ModelEntry[]>([])
const activeCamId = ref(0)
let nextCamId = 1
let nextModelId = 1

let renderer: THREE.WebGLRenderer | null = null
let thumbRenderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let editorCam: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let transformCtrl: TransformControls | null = null
let animId: number | null = null
let resizeObserver: ResizeObserver | null = null
let justDragged = false
let thumbDirty = false
let mouseDownPos = { x: 0, y: 0 }

// 骨骼节点 gizmo
const selectedBone = ref<BoneEntry | null>(null)
let boneGizmoMap = new Map<THREE.Bone, THREE.Mesh>()
let boneGizmoGeo: THREE.SphereGeometry | null = null
let boneGizmoMat: THREE.MeshBasicMaterial | null = null
let boneGizmoMatSel: THREE.MeshBasicMaterial | null = null

// 当前选中的对象（模型或相机辅助体）
const selectedId = ref<{ type: 'model' | 'cam'; id: number } | null>(null)
// 变换模式
const transformMode = ref<'translate' | 'rotate'>('translate')
// 双击放大预览
const zoomedCamId = ref<number | null>(null)
const zoomedUrl = ref('')

// ── 几何构建（保留方块备用）──
function buildCube(): THREE.Group {
  const g = new THREE.Group()
  g.add(new THREE.Mesh(new THREE.BoxGeometry(1,1,1), new THREE.MeshStandardMaterial({ color: 0x6c63ff })))
  return g
}

// ── 场景 ──
function initScene() {
  const canvas = mainCanvasRef.value; if (!canvas) return
  scene = new THREE.Scene(); scene.background = new THREE.Color(0x141420)

  const w = window.innerWidth - 400
  const h = window.innerHeight
  editorCam = new THREE.PerspectiveCamera(45, w/h, 0.01, 500)
  editorCam.position.set(0, 1.5, 4)

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true })
  renderer.setPixelRatio(window.devicePixelRatio)
  renderer.setSize(w, h, false)
  renderer.shadowMap.enabled = true

  // 跟随容器尺寸变化
  resizeObserver = new ResizeObserver(() => {
    const c = mainCanvasRef.value; if (!c || !renderer || !editorCam) return
    const nw = c.clientWidth, nh = c.clientHeight
    renderer.setSize(nw, nh, false)
    editorCam.aspect = nw / nh; editorCam.updateProjectionMatrix()
  })
  resizeObserver.observe(canvas)

  scene.add(new THREE.AmbientLight(0xffffff, 0.7))
  const dir = new THREE.DirectionalLight(0xffffff, 1.2); dir.position.set(5,8,5); dir.castShadow = true; scene.add(dir)
  scene.add(new THREE.DirectionalLight(0x8888ff, 0.35).clone().translateTo?.(-5,2,-5) ?? (() => { const l = new THREE.DirectionalLight(0x8888ff,.35); l.position.set(-5,2,-5); return l })())

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(20,20), new THREE.MeshStandardMaterial({ color: 0x1a1a2e }))
  floor.rotation.x = -Math.PI/2; floor.receiveShadow = true; scene.add(floor)
  scene.add(new THREE.GridHelper(20, 40, 0x333355, 0x222244))

  controls = new OrbitControls(editorCam, canvas); controls.enableDamping = true; controls.dampingFactor = 0.08
  controls.target.set(0, 0.8, 0); controls.update()

  // TransformControls
  transformCtrl = new TransformControls(editorCam, canvas)
  transformCtrl.setMode('translate')
  transformCtrl.addEventListener('dragging-changed', e => {
    if (controls) controls.enabled = !e.value
    if (!e.value) justDragged = true  // 拖拽结束，屏蔽下一次 click
  })
  transformCtrl.addEventListener('objectChange', () => {
    thumbDirty = true
    // 骨骼旋转时同步回 BoneEntry
    if (selectedBone.value) {
      const be = selectedBone.value
      be.rx = THREE.MathUtils.radToDeg(be.bone.rotation.x)
      be.ry = THREE.MathUtils.radToDeg(be.bone.rotation.y)
      be.rz = THREE.MathUtils.radToDeg(be.bone.rotation.z)
      return
    }
    if (!selectedId.value) return
    const sel = selectedId.value
    if (sel.type === 'model') {
      const m = models.value.find(m => m.id === sel.id)
      if (m) {
        m.px = m.obj.position.x; m.py = m.obj.position.y; m.pz = m.obj.position.z
        m.rx = THREE.MathUtils.radToDeg(m.obj.rotation.x)
        m.ry = THREE.MathUtils.radToDeg(m.obj.rotation.y)
        m.rz = THREE.MathUtils.radToDeg(m.obj.rotation.z)
      }
    } else {
      const ce = cameras.value.find(c => c.id === sel.id)
      if (ce) {
        ce.px = ce.cam.position.x; ce.py = ce.cam.position.y; ce.pz = ce.cam.position.z
        ce.rx = THREE.MathUtils.radToDeg(ce.cam.rotation.x)
        ce.ry = THREE.MathUtils.radToDeg(ce.cam.rotation.y)
        ce.rz = THREE.MathUtils.radToDeg(ce.cam.rotation.z)
        ce.helper.update()
      }
    }
  })
  scene.add(transformCtrl.getHelper())

  // 骨骼 gizmo 共享几何体与材质
  boneGizmoGeo = new THREE.SphereGeometry(0.035, 8, 8)
  boneGizmoMat = new THREE.MeshBasicMaterial({ color: 0xffdd00, depthTest: false })
  boneGizmoMatSel = new THREE.MeshBasicMaterial({ color: 0xff4400, depthTest: false })

  // 点击选中（mousedown 记录位置，click 时判断是否真的是点击而非拖拽旋转）
  canvas.addEventListener('mousedown', e => { mouseDownPos = { x: e.clientX, y: e.clientY } })
  canvas.addEventListener('click', onCanvasClick)

  // 离屏缩略图渲染器（复用，避免每帧 new WebGLRenderer）
  const offscreen = document.createElement('canvas')
  offscreen.width = 180; offscreen.height = 120
  thumbRenderer = new THREE.WebGLRenderer({ canvas: offscreen, antialias: false, preserveDrawingBuffer: true })
  thumbRenderer.setSize(180, 120)

  // 添加默认模型和相机
  addPresetModel('male')
  addCamera()
  loop()
}

function loop() {
  animId = requestAnimationFrame(loop)
  controls?.update()
  if (!scene || !editorCam || !renderer) return
  // 每帧同步骨骼 gizmo 小球到骨骼世界坐标
  const worldPos = new THREE.Vector3()
  for (const [bone, mesh] of boneGizmoMap) {
    bone.getWorldPosition(worldPos)
    mesh.position.copy(worldPos)
  }
  renderer.render(scene, editorCam)
  if (thumbDirty) {
    cameras.value.forEach(ce => renderThumb(ce))
    thumbDirty = false
  }
}

function renderThumb(ce: CamEntry) {
  if (!scene || !thumbRenderer) return
  const tcHelper = transformCtrl?.getHelper()
  if (tcHelper) tcHelper.visible = false
  cameras.value.forEach(c => { c.helper.visible = false })
  for (const mesh of boneGizmoMap.values()) mesh.visible = false
  thumbRenderer.render(scene, ce.cam)
  if (tcHelper) tcHelper.visible = true
  cameras.value.forEach(c => { c.helper.visible = true })
  for (const mesh of boneGizmoMap.values()) mesh.visible = true
  ce.thumbUrl = thumbRenderer.domElement.toDataURL('image/jpeg', 0.7)
}

function onCanvasClick(e: MouseEvent) {
  if (!scene || !editorCam || !renderer || !transformCtrl) return
  if (justDragged) { justDragged = false; return }
  if (transformCtrl.dragging) return
  const dx = e.clientX - mouseDownPos.x
  const dy = e.clientY - mouseDownPos.y
  if (dx * dx + dy * dy > 25) return
  const rect = renderer.domElement.getBoundingClientRect()
  const mouse = new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1
  )
  const raycaster = new THREE.Raycaster()
  raycaster.setFromCamera(mouse, editorCam)

  // 先检测骨骼 gizmo（当前有模型选中时才检测）
  if (boneGizmoMap.size > 0) {
    const gizmoMeshes = Array.from(boneGizmoMap.values())
    const boneHits = raycaster.intersectObjects(gizmoMeshes, false)
    if (boneHits.length) {
      const hitMesh = boneHits[0].object as THREE.Mesh
      for (const [bone, mesh] of boneGizmoMap) {
        if (mesh === hitMesh) {
          // 找到对应 BoneEntry
          for (const m of models.value) {
            const be = m.bones.find(b => b.bone === bone)
            if (be) { selectBone(be); return }
          }
        }
      }
    }
  }

  // 先检测模型，再检测相机，避免 CameraHelper 子对象优先被命中
  const modelMeshes: THREE.Object3D[] = []
  models.value.forEach(m => {
    toRaw(m.obj).traverse(child => {
      if ((child as THREE.Mesh).isMesh) modelMeshes.push(child)
    })
  })
  const modelHits = raycaster.intersectObjects(modelMeshes, false)
  if (modelHits.length) {
    const hit = modelHits[0].object
    for (const m of models.value) {
      if (isDescendant(toRaw(m.obj), hit)) { attachTo(m.obj, 'model', m.id); return }
    }
  }

  // 检测相机辅助体
  const camHelpers = cameras.value.map(c => c.helper)
  const camHits = raycaster.intersectObjects(camHelpers, true)
  if (camHits.length) {
    const hit = camHits[0].object
    for (const ce of cameras.value) {
      if (isDescendant(ce.helper, hit)) { attachTo(ce.cam, 'cam', ce.id); return }
    }
  }

  // 点击空白区域取消选择
  transformCtrl.detach(); selectedId.value = null
  hideBoneGizmos(); selectedBone.value = null
}

function isDescendant(root: THREE.Object3D, target: THREE.Object3D): boolean {
  let cur: THREE.Object3D | null = target
  while (cur) { if (cur === root) return true; cur = cur.parent }
  return false
}

function attachTo(obj: THREE.Object3D, type: 'model' | 'cam', id: number) {
  if (!transformCtrl) return
  // 切换到非骨骼对象时清除骨骼选中状态
  hideBoneGizmos()
  selectedBone.value = null
  transformCtrl.setMode(transformMode.value)
  transformCtrl.attach(obj)
  selectedId.value = { type, id }
  if (type === 'model') {
    const m = models.value.find(m => m.id === id)
    if (m) showBoneGizmos(m)
  }
}

function showBoneGizmos(m: ModelEntry) {
  if (!scene || !boneGizmoGeo || !boneGizmoMat) return
  hideBoneGizmos()
  for (const be of m.bones) {
    // 每个骨骼独立材质实例，避免颜色状态共享
    const mat = boneGizmoMat.clone()
    const mesh = new THREE.Mesh(boneGizmoGeo, mat)
    mesh.renderOrder = 999
    scene.add(mesh)
    boneGizmoMap.set(be.bone, mesh)
  }
}

function hideBoneGizmos() {
  if (!scene) return
  for (const mesh of boneGizmoMap.values()) {
    scene.remove(mesh)
    ;(mesh.material as THREE.Material).dispose()
  }
  boneGizmoMap.clear()
}

function selectBone(be: BoneEntry) {
  if (!transformCtrl) return
  // 恢复上一个选中骨骼的颜色
  if (selectedBone.value) {
    const prevMesh = boneGizmoMap.get(selectedBone.value.bone)
    if (prevMesh) (prevMesh.material as THREE.MeshBasicMaterial).color.setHex(0xffdd00)
  }
  selectedBone.value = be
  const mesh = boneGizmoMap.get(be.bone)
  if (mesh) (mesh.material as THREE.MeshBasicMaterial).color.setHex(0xff4400)
  // 把 TransformControls 挂到骨骼上，仅旋转模式
  transformCtrl.setMode('rotate')
  transformCtrl.attach(be.bone)
}

function setTransformMode(mode: 'translate' | 'rotate') {
  transformMode.value = mode
  transformCtrl?.setMode(mode)
}

function deselectAll() {
  transformCtrl?.detach()
  selectedId.value = null
  hideBoneGizmos()
  selectedBone.value = null
  transformCtrl?.setMode(transformMode.value)
}

function destroyScene() {
  if (animId !== null) { cancelAnimationFrame(animId); animId = null }
  resizeObserver?.disconnect(); resizeObserver = null
  mainCanvasRef.value?.removeEventListener('click', onCanvasClick)
  hideBoneGizmos()
  boneGizmoGeo?.dispose(); boneGizmoGeo = null
  boneGizmoMat?.dispose(); boneGizmoMat = null
  boneGizmoMatSel?.dispose(); boneGizmoMatSel = null
  selectedBone.value = null
  transformCtrl?.detach(); transformCtrl?.dispose(); transformCtrl = null
  controls?.dispose(); renderer?.dispose(); thumbRenderer?.dispose()
  renderer = null; thumbRenderer = null; scene = null; editorCam = null; controls = null
  cameras.value = []; models.value = []; nextCamId = 1; nextModelId = 1
  selectedId.value = null
}

// ── 模型管理 ──
function addPresetModel(key: string) {
  if (!scene) return
  const labels: Record<string,string> = { cube:'正方体', male:'男模', female:'女模' }

  if (key === 'male' || key === 'female') {
    const url = key === 'male' ? '/3D/man.glb' : '/3D/woman.glb'
    const label = `${labels[key]} ${nextModelId}`
    const loader1 = new GLTFLoader(); loader1.setMeshoptDecoder(MeshoptDecoder)
    loader1.load(url, gltf => { addUploadedModel(gltf.scene, label) })
    return
  }

  // cube
  const obj = buildCube()
  const id = nextModelId++
  const entry: ModelEntry = { id, label: `正方体 ${id}`, obj, px: (models.value.length % 3 - 1) * 1.2, py: 0, pz: 0, rx: 0, ry: 0, rz: 0, bones: [] }
  obj.position.set(entry.px, entry.py, entry.pz)
  scene.add(obj); models.value.push(entry)
}

function downsampleTexture(tex: THREE.Texture, maxSize = 1024) {
  const img = tex.image as HTMLImageElement | HTMLCanvasElement | ImageBitmap
  if (!img) return
  const w = (img as HTMLImageElement).width ?? (img as HTMLCanvasElement).width
  const h = (img as HTMLImageElement).height ?? (img as HTMLCanvasElement).height
  if (!w || !h || (w <= maxSize && h <= maxSize)) return
  const scale = maxSize / Math.max(w, h)
  const cv = document.createElement('canvas')
  cv.width = Math.round(w * scale); cv.height = Math.round(h * scale)
  cv.getContext('2d')!.drawImage(img as CanvasImageSource, 0, 0, cv.width, cv.height)
  tex.image = cv; tex.needsUpdate = true
}

function simplifyMaterials(obj: THREE.Group) {
  obj.traverse(child => {
    const mesh = child as THREE.Mesh
    if (!mesh.isMesh) return
    const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    const next = mats.map(mat => {
      const src = mat as THREE.MeshPhysicalMaterial
      if (!(mat instanceof THREE.MeshPhysicalMaterial)) {
        // 仅降采样纹理
        ;[src.map, src.normalMap, src.roughnessMap, src.metalnessMap].forEach(t => { if (t) downsampleTexture(t) })
        return mat
      }
      const std = new THREE.MeshStandardMaterial({
        map: src.map, normalMap: src.normalMap,
        roughnessMap: src.roughnessMap, metalnessMap: src.metalnessMap,
        color: src.color, roughness: src.roughness, metalness: src.metalness,
        transparent: src.transparent, opacity: src.opacity,
        side: src.side, alphaTest: src.alphaTest,
      })
      ;[std.map, std.normalMap, std.roughnessMap, std.metalnessMap].forEach(t => { if (t) downsampleTexture(t) })
      src.dispose()
      return std
    })
    mesh.material = Array.isArray(mesh.material) ? next : next[0]
  })
}

function normalizeModelHeight(obj: THREE.Group, targetHeight = 1.75) {
  const box = new THREE.Box3().setFromObject(obj)
  const size = box.getSize(new THREE.Vector3())
  if (size.y > 0) {
    const s = targetHeight / size.y
    obj.scale.set(s, s, s)
    // 重新计算，让底部落在 y=0
    const box2 = new THREE.Box3().setFromObject(obj)
    obj.position.y -= box2.min.y
  }
}

// 站姿：手臂自然下垂，略微外展
const DEFAULT_POSE: Record<string, [number, number, number]> = {
  LeftArm:  [70, 0, 0],
  RightArm: [70, 0, 0],
}

function applyDefaultPose(obj: THREE.Group) {
  obj.traverse(child => {
    if (!(child as THREE.Bone).isBone) return
    for (const key of Object.keys(DEFAULT_POSE)) {
      if (child.name === key || child.name.endsWith(key)) {
        const [rx, ry, rz] = DEFAULT_POSE[key]
        child.rotation.set(
          THREE.MathUtils.degToRad(rx),
          THREE.MathUtils.degToRad(ry),
          THREE.MathUtils.degToRad(rz)
        )
        break
      }
    }
  })
}

function extractBones(obj: THREE.Group): BoneEntry[] {
  const result: BoneEntry[] = []
  const seen = new Set<string>()
  obj.traverse(child => {
    if (!(child as THREE.Bone).isBone) return
    // 只保留 BONE_MAP 中有明确映射的骨骼，跳过手指/趾等细节骨骼
    const matched = Object.keys(BONE_MAP).find(key => child.name === key || child.name.endsWith(key))
    if (!matched) return
    const display = getBoneDisplay(child.name)
    if (seen.has(display.label)) return  // 去重，同一中文名只取第一个
    seen.add(display.label)
    result.push({
      name: child.name,
      bone: child as THREE.Bone,
      rx: THREE.MathUtils.radToDeg(child.rotation.x),
      ry: THREE.MathUtils.radToDeg(child.rotation.y),
      rz: THREE.MathUtils.radToDeg(child.rotation.z),
    })
  })
  return result
}

function addUploadedModel(obj: THREE.Group, name: string) {
  if (!scene) return
  simplifyMaterials(obj)
  normalizeModelHeight(obj)
  applyDefaultPose(obj)
  const bones = extractBones(obj)
  const id = nextModelId++
  const entry: ModelEntry = { id, label: name, obj, px: (models.value.length % 3 - 1) * 1.5, py: 0, pz: 0, rx: 0, ry: 0, rz: 0, bones }
  obj.position.x = entry.px; obj.position.z = entry.pz
  scene.add(obj); models.value.push(entry)
  thumbDirty = true
}

function removeModel(id: number) {
  const entry = models.value.find(m => m.id === id); if (!entry) return
  if (selectedId.value?.id === id && selectedId.value?.type === 'model') {
    transformCtrl?.detach(); selectedId.value = null
    hideBoneGizmos(); selectedBone.value = null
  }
  // 若当前选中骨骼属于此模型，也清除
  if (selectedBone.value && entry.bones.some(b => b === selectedBone.value)) {
    transformCtrl?.detach(); selectedBone.value = null
    hideBoneGizmos()
  }
  const rawObj = toRaw(entry.obj)
  scene?.remove(rawObj)
  rawObj.traverse(c => {
    if ((c as THREE.Mesh).isMesh) {
      (c as THREE.Mesh).geometry?.dispose()
    }
  })
  models.value = models.value.filter(m => m.id !== id)
}


function updateModelTransform(entry: ModelEntry) {
  entry.obj.position.set(entry.px, entry.py, entry.pz)
  entry.obj.rotation.set(
    THREE.MathUtils.degToRad(entry.rx),
    THREE.MathUtils.degToRad(entry.ry),
    THREE.MathUtils.degToRad(entry.rz)
  )
}

// 对焦选中对象
function focusObject(obj: THREE.Object3D) {
  if (!controls || !editorCam) return
  const box = new THREE.Box3().setFromObject(obj)
  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3()).length()
  controls.target.copy(center)
  const dir = editorCam.position.clone().sub(center).normalize()
  editorCam.position.copy(center.clone().add(dir.multiplyScalar(size * 1.8)))
  controls.update()
}

function selectFromTree(type: 'model' | 'cam', id: number) {
  if (type === 'model') {
    const m = models.value.find(m => m.id === id); if (!m) return
    attachTo(m.obj, 'model', id)
    focusObject(m.obj)
  } else {
    const ce = cameras.value.find(c => c.id === id); if (!ce) return
    attachTo(ce.cam, 'cam', id)
    activeCamId.value = id
    // 对焦到相机位置附近，避免 CameraHelper 包围盒异常
    if (controls && editorCam) {
      controls.target.copy(ce.cam.position)
      const dir = editorCam.position.clone().sub(ce.cam.position).normalize()
      if (dir.length() < 0.001) dir.set(0, 0.5, 1).normalize()
      editorCam.position.copy(ce.cam.position.clone().add(dir.multiplyScalar(3)))
      controls.update()
    }
  }
}

// ── 相机管理 ──
function addCamera() {
  const id = nextCamId++
  const cam = new THREE.PerspectiveCamera(45, 180/120, 0.01, 500)
  const offset = cameras.value.length
  const px = 0, py = 1.5, pz = 3 + offset * 0.5
  cam.position.set(px, py, pz); cam.lookAt(0, 0.8, 0)
  const helper = new THREE.CameraHelper(cam)
  scene?.add(cam)
  scene?.add(helper)
  const entry: CamEntry = { id, label: `相机 ${id}`, cam, helper, thumbUrl: '', px, py, pz, rx: 0, ry: 0, rz: 0, fov: 45 }
  cameras.value.push(entry)
  if (cameras.value.length === 1) activeCamId.value = id
  thumbDirty = true
}

function removeCamera(id: number) {
  if (cameras.value.length <= 1) return
  const ce = cameras.value.find(c => c.id === id); if (!ce) return
  if (selectedId.value?.id === id) { transformCtrl?.detach(); selectedId.value = null }
  const rawHelper = toRaw(ce.helper)
  const rawCam = toRaw(ce.cam)
  scene?.remove(rawHelper); rawHelper.dispose()
  scene?.remove(rawCam)
  cameras.value = cameras.value.filter(c => c.id !== id)
  if (activeCamId.value === id) activeCamId.value = cameras.value[0]?.id ?? 0
}

function zoomCam(ce: CamEntry) {
  if (!scene || !thumbRenderer) return
  thumbRenderer.setSize(640, 426)
  const tcHelper = transformCtrl?.getHelper()
  if (tcHelper) tcHelper.visible = false
  cameras.value.forEach(c => { c.helper.visible = false })
  for (const mesh of boneGizmoMap.values()) mesh.visible = false
  thumbRenderer.render(scene, ce.cam)
  if (tcHelper) tcHelper.visible = true
  cameras.value.forEach(c => { c.helper.visible = true })
  for (const mesh of boneGizmoMap.values()) mesh.visible = true
  zoomedUrl.value = thumbRenderer.domElement.toDataURL('image/jpeg', 0.9)
  thumbRenderer.setSize(180, 120)
  zoomedCamId.value = ce.id
}

function updateBone(be: BoneEntry) {
  be.bone.rotation.set(
    THREE.MathUtils.degToRad(be.rx),
    THREE.MathUtils.degToRad(be.ry),
    THREE.MathUtils.degToRad(be.rz)
  )
  thumbDirty = true
}

function updateCamTransform(ce: CamEntry) {
  ce.cam.position.set(ce.px, ce.py, ce.pz)
  ce.cam.rotation.set(
    THREE.MathUtils.degToRad(ce.rx),
    THREE.MathUtils.degToRad(ce.ry),
    THREE.MathUtils.degToRad(ce.rz)
  )
  ce.cam.fov = ce.fov
  ce.cam.updateProjectionMatrix()
  ce.helper.update()
  thumbDirty = true
}

// ── 上传 ──
function onFileInput(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]; if (!file) return
  loadModelFile(file); (e.target as HTMLInputElement).value = ''
}
function onDrop(e: DragEvent) {
  const file = e.dataTransfer?.files[0]; if (file) loadModelFile(file)
}
function loadModelFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['glb','gltf','obj'].includes(ext ?? '')) return
  const url = URL.createObjectURL(file)
  if (ext === 'obj') {
    new OBJLoader().load(url, obj => { obj.traverse(c => { if ((c as THREE.Mesh).isMesh) (c as THREE.Mesh).material = new THREE.MeshStandardMaterial({ color: 0x888888 }) }); addUploadedModel(obj, file.name); URL.revokeObjectURL(url) })
  } else {
    const loader2 = new GLTFLoader(); loader2.setMeshoptDecoder(MeshoptDecoder)
    loader2.load(url, gltf => { addUploadedModel(gltf.scene, file.name); URL.revokeObjectURL(url) })
  }
}

// ── 截图 ──
async function capture() {
  if (!scene || !renderer) return
  const canvas = mainCanvasRef.value
  const origW = canvas?.clientWidth ?? 1200
  const origH = canvas?.clientHeight ?? 700

  const tcHelper = transformCtrl?.getHelper()
  if (tcHelper) tcHelper.visible = false
  cameras.value.forEach(c => { c.helper.visible = false })
  // 隐藏骨骼 gizmo
  for (const mesh of boneGizmoMap.values()) mesh.visible = false

  for (const ce of cameras.value) {
    const origAspect = ce.cam.aspect
    ce.cam.aspect = 1920 / 1080
    ce.cam.updateProjectionMatrix()
    renderer.setSize(1920, 1080, false)
    renderer.render(scene, ce.cam)
    await new Promise<void>(resolve => {
      renderer!.domElement.toBlob(blob => {
        if (blob) emit('capture', new File([blob], `cam${ce.id}-${Date.now()}.png`, { type: 'image/png' }))
        resolve()
      }, 'image/png')
    })
    ce.cam.aspect = origAspect
    ce.cam.updateProjectionMatrix()
  }

  if (tcHelper) tcHelper.visible = true
  cameras.value.forEach(c => { c.helper.visible = true })
  for (const mesh of boneGizmoMap.values()) mesh.visible = true
  renderer.setSize(origW, origH, false)
  emit('update:visible', false)
}

watch(() => props.visible, val => { if (val) setTimeout(initScene, 60); else destroyScene() })
onBeforeUnmount(destroyScene)
</script>

<template>
  <teleport to="body">
    <transition name="mv-fade">
      <div v-if="visible" class="mv-overlay">
        <div class="mv-root">

          <!-- ── 左侧：场景树 ── -->
          <div class="mv-tree">
            <div class="tree-header">
              <span class="tree-title">场景</span>
              <button class="close-btn" @click="emit('update:visible', false)">✕</button>
            </div>

            <!-- 添加按钮 -->
            <div class="tree-add-row">
              <button class="add-btn" @click="addCamera">+ 机位</button>
              <div class="add-model-group">
                <button class="add-btn" @click="addPresetModel('male')">男模</button>
                <button class="add-btn" @click="addPresetModel('female')">女模</button>
                <label class="add-btn">
                  <input type="file" accept=".glb,.gltf,.obj" @change="onFileInput" hidden />
                  上传
                </label>
              </div>
            </div>

            <!-- 机位列表 -->
            <div class="tree-section-label">机位</div>
            <div
              v-for="ce in cameras" :key="ce.id"
              class="tree-item"
              :class="{ selected: selectedId?.id === ce.id && selectedId?.type === 'cam' }"
              @click="selectFromTree('cam', ce.id)"
            >
              <div class="tree-item-top">
                <span class="tree-icon">📷</span>
                <span class="tree-name">{{ ce.label }}</span>
                <span class="active-dot" v-if="activeCamId === ce.id" title="当前截图机位" />
                <button class="tree-del" @click.stop="removeCamera(ce.id)" v-if="cameras.length > 1">×</button>
              </div>
            </div>

            <!-- 模型列表 -->
            <div class="tree-section-label" v-if="models.length">模型</div>
            <div
              v-for="m in models" :key="m.id"
              class="tree-item"
              :class="{ selected: selectedId?.id === m.id && selectedId?.type === 'model' }"
              @click="selectFromTree('model', m.id)"
            >
              <div class="tree-item-top">
                <span class="tree-icon">⬜</span>
                <span class="tree-name">{{ m.label }}</span>
                <button class="tree-del" @click.stop="removeModel(m.id)">×</button>
              </div>
            </div>
          </div>

          <!-- ── 中间：主视口 ── -->
          <div class="mv-main" @dragover.prevent @drop.prevent="onDrop">
            <canvas ref="mainCanvasRef" class="mv-canvas" />
            <div class="mv-toolbar">
              <button class="tb-btn" :class="{ active: transformMode === 'translate' }" @click="setTransformMode('translate')">移动</button>
              <button class="tb-btn" :class="{ active: transformMode === 'rotate' }" @click="setTransformMode('rotate')">旋转</button>
              <button class="tb-btn desel" @click="deselectAll" v-if="selectedId || selectedBone">取消选择</button>
            </div>
            <div class="mv-hint" v-if="selectedBone">骨骼模式：拖动旋转手柄调整姿态 · 点击其他骨骼切换</div>
            <div class="mv-hint" v-else>点击模型/机位选中 · 左键旋转视角 · 右键平移 · 滚轮缩放</div>
          </div>

          <!-- ── 右侧：属性面板 ── -->
          <div class="mv-props">
            <div class="props-header">属性</div>

            <!-- 无选中 -->
            <div v-if="!selectedId" class="props-empty">点击左侧选中对象</div>

            <!-- 相机属性 -->
            <template v-if="selectedId?.type === 'cam'">
              <div v-for="ce in cameras.filter(c => c.id === selectedId?.id)" :key="ce.id">
                <div class="props-name">{{ ce.label }}</div>
                <img v-if="ce.thumbUrl" :src="ce.thumbUrl" class="props-thumb" title="双击放大" @dblclick="zoomCam(ce)" />
                <div class="props-group-label">位置</div>
                <div class="props-row"><span>X</span><input type="number" v-model.number="ce.px" step="0.01" @input="updateCamTransform(ce)" /></div>
                <div class="props-row"><span>Y</span><input type="number" v-model.number="ce.py" step="0.01" @input="updateCamTransform(ce)" /></div>
                <div class="props-row"><span>Z</span><input type="number" v-model.number="ce.pz" step="0.01" @input="updateCamTransform(ce)" /></div>
                <div class="props-group-label">旋转（度）</div>
                <div class="props-row"><span>俯仰</span><input type="number" v-model.number="ce.rx" step="1" @input="updateCamTransform(ce)" /></div>
                <div class="props-row"><span>偏转</span><input type="number" v-model.number="ce.ry" step="1" @input="updateCamTransform(ce)" /></div>
                <div class="props-row"><span>横滚</span><input type="number" v-model.number="ce.rz" step="1" @input="updateCamTransform(ce)" /></div>
                <div class="props-group-label">焦距</div>
                <div class="props-row">
                  <span>FOV</span>
                  <input type="range" min="10" max="120" step="1" v-model.number="ce.fov" @input="updateCamTransform(ce)" class="fov-slider" />
                  <input type="number" min="10" max="120" step="1" v-model.number="ce.fov" @change="updateCamTransform(ce)" class="fov-num" />
                </div>
                <div class="props-group-label">截图机位</div>
                <button class="set-active-btn" @click="activeCamId = ce.id" :class="{ on: activeCamId === ce.id }">
                  {{ activeCamId === ce.id ? '✓ 当前机位' : '设为截图机位' }}
                </button>
              </div>
            </template>

            <!-- 模型属性 -->
            <template v-if="selectedId?.type === 'model'">
              <div v-for="m in models.filter(m => m.id === selectedId?.id)" :key="m.id">
                <div class="props-name">{{ m.label }}</div>
                <div class="props-group-label">位置</div>
                <div class="props-row"><span>X</span><input type="number" v-model.number="m.px" step="0.01" @input="updateModelTransform(m)" /></div>
                <div class="props-row"><span>Y</span><input type="number" v-model.number="m.py" step="0.01" @input="updateModelTransform(m)" /></div>
                <div class="props-row"><span>Z</span><input type="number" v-model.number="m.pz" step="0.01" @input="updateModelTransform(m)" /></div>
                <div class="props-group-label">旋转（度）</div>
                <div class="props-row"><span>X</span><input type="number" v-model.number="m.rx" step="1" @input="updateModelTransform(m)" /></div>
                <div class="props-row"><span>Y</span><input type="number" v-model.number="m.ry" step="1" @input="updateModelTransform(m)" /></div>
                <div class="props-row"><span>Z</span><input type="number" v-model.number="m.rz" step="1" @input="updateModelTransform(m)" /></div>
                <template v-if="m.bones.length">
                  <div class="props-group-label">骨骼姿态 <span class="bone-hint">（点击名称在场景中选中）</span></div>
                  <div v-for="be in m.bones" :key="be.name" class="bone-block"
                    :class="{ 'bone-selected': selectedBone === be }"
                    @click="selectBone(be)"
                  >
                    <div class="bone-name">{{ getBoneDisplay(be.name).label }}</div>
                    <div class="bone-row" v-for="(axisLabel, ai) in getBoneDisplay(be.name).axes" :key="ai">
                      <span class="bone-axis">{{ axisLabel }}</span>
                      <input type="range" min="-180" max="180" step="1"
                        :value="ai === 0 ? be.rx : ai === 1 ? be.ry : be.rz"
                        @input="e => { const v = +( e.target as HTMLInputElement).value; if(ai===0) be.rx=v; else if(ai===1) be.ry=v; else be.rz=v; updateBone(be) }"
                        class="bone-slider"
                        @click.stop
                      />
                      <input type="number" min="-180" max="180" step="1"
                        :value="ai === 0 ? be.rx : ai === 1 ? be.ry : be.rz"
                        @change="e => { const v = +( e.target as HTMLInputElement).value; if(ai===0) be.rx=v; else if(ai===1) be.ry=v; else be.rz=v; updateBone(be) }"
                        class="bone-num"
                        @click.stop
                      />
                    </div>
                  </div>
                </template>
              </div>
            </template>

            <!-- 截图按钮 -->
            <button class="capture-btn" :disabled="cameras.length === 0" @click="capture">
              截取当前机位视角
            </button>
          </div>

        </div>
      </div>
    </transition>

    <!-- 双击放大预览 -->
    <div v-if="zoomedCamId !== null" class="zoom-overlay" @click="zoomedCamId = null">
      <img :src="zoomedUrl" class="zoom-img" />
      <span class="zoom-hint">点击任意处关闭</span>
    </div>
  </teleport>
</template>

<style scoped>
.mv-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: #0d0d1a; display: flex;
}
.mv-fade-enter-active, .mv-fade-leave-active { transition: opacity 0.2s; }
.mv-fade-enter-from, .mv-fade-leave-to { opacity: 0; }

.mv-root { display: flex; width: 100%; height: 100vh; }

/* ── 左侧场景树 ── */
.mv-tree {
  width: 200px; flex-shrink: 0;
  display: flex; flex-direction: column;
  background: #0a0a18;
  border-right: 1px solid rgba(255,255,255,0.06);
  overflow-y: auto; height: 100vh;
}
.tree-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.06);
  position: sticky; top: 0; background: #0a0a18; z-index: 1;
}
.tree-title { font-size: 12px; color: rgba(255,255,255,0.5); font-weight: 500; letter-spacing: 1px; }
.close-btn {
  background: none; border: none; color: rgba(255,255,255,0.3);
  font-size: 14px; cursor: pointer; padding: 2px 5px; border-radius: 4px;
}
.close-btn:hover { color: #f87171; background: rgba(248,113,113,0.1); }

.tree-add-row { padding: 8px 8px 4px; display: flex; flex-direction: column; gap: 4px; }
.add-model-group { display: flex; flex-wrap: wrap; gap: 4px; }
.add-btn {
  padding: 3px 8px; border-radius: 5px; font-size: 11px;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.6); cursor: pointer; transition: all 0.15s;
}
.add-btn:hover { border-color: rgba(108,99,255,0.5); color: #fff; background: rgba(108,99,255,0.12); }

.tree-section-label {
  font-size: 10px; color: rgba(255,255,255,0.25);
  padding: 6px 10px 3px; letter-spacing: 1px; text-transform: uppercase;
}

.tree-item {
  padding: 6px 8px; cursor: pointer;
  border-left: 2px solid transparent;
  transition: all 0.15s;
}
.tree-item:hover { background: rgba(255,255,255,0.03); }
.tree-item.selected { background: rgba(108,99,255,0.08); border-left-color: #6c63ff; }

.tree-item-top {
  display: flex; align-items: center; gap: 5px; min-height: 22px;
}
.tree-icon { font-size: 11px; opacity: 0.6; }
.tree-name { font-size: 12px; color: rgba(255,255,255,0.7); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.active-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #a78bfa; flex-shrink: 0;
}
.tree-del {
  background: none; border: none; color: rgba(255,255,255,0.2);
  font-size: 14px; cursor: pointer; padding: 0 2px; line-height: 1;
  flex-shrink: 0; transition: color 0.15s;
}
.tree-del:hover { color: #f87171; }

.thumb-canvas {
  width: 100%; height: auto; display: block;
  border-radius: 4px; margin-top: 5px;
  background: #111;
}

/* ── 中间视口 ── */
.mv-main { flex: 1; height: 100vh; position: relative; min-width: 0; }
.mv-canvas { width: 100%; height: 100%; display: block; }

.mv-toolbar {
  position: absolute; top: 14px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 6px;
  background: rgba(13,13,26,0.8); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; padding: 4px 8px; backdrop-filter: blur(8px);
}
.tb-btn {
  padding: 4px 14px; border-radius: 5px;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04);
  color: rgba(255,255,255,0.55); font-size: 12px; cursor: pointer; transition: all 0.15s;
}
.tb-btn:hover { color: #fff; background: rgba(255,255,255,0.08); }
.tb-btn.active { background: rgba(108,99,255,0.25); border-color: rgba(108,99,255,0.6); color: #fff; }
.tb-btn.desel { border-color: rgba(248,113,113,0.4); color: rgba(248,113,113,0.7); }
.tb-btn.desel:hover { background: rgba(248,113,113,0.1); color: #f87171; }

.mv-hint {
  position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%);
  font-size: 11px; color: rgba(255,255,255,0.15); pointer-events: none;
  white-space: nowrap; letter-spacing: 0.4px;
}

/* ── 右侧属性面板 ── */
.mv-props {
  width: 200px; flex-shrink: 0; height: 100vh; box-sizing: border-box;
  display: flex; flex-direction: column;
  background: #0a0a18; border-left: 1px solid rgba(255,255,255,0.06);
  padding: 0 10px 12px; overflow-y: auto;
}
.props-header {
  font-size: 11px; color: rgba(255,255,255,0.35); letter-spacing: 1px;
  padding: 14px 2px 10px; border-bottom: 1px solid rgba(255,255,255,0.06);
  margin-bottom: 12px; position: sticky; top: 0; background: #0a0a18; z-index: 1;
}
.props-empty { font-size: 11px; color: rgba(255,255,255,0.2); padding: 8px 2px; }
.props-name { font-size: 13px; color: rgba(255,255,255,0.8); font-weight: 500; margin-bottom: 10px; }
.props-group-label {
  font-size: 10px; color: rgba(255,255,255,0.25); letter-spacing: 1px;
  margin: 10px 0 4px; text-transform: uppercase;
}
.props-row {
  display: flex; align-items: center; gap: 8px; margin-bottom: 4px;
}
.props-row span {
  font-size: 11px; color: rgba(255,255,255,0.35); width: 28px; flex-shrink: 0; text-align: right;
}
.props-row input {
  flex: 1; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; color: rgba(255,255,255,0.85); font-size: 11px;
  padding: 3px 6px; outline: none; -moz-appearance: textfield;
}
.props-row input::-webkit-outer-spin-button,
.props-row input::-webkit-inner-spin-button { -webkit-appearance: none; }
.props-row input:focus { border-color: rgba(108,99,255,0.5); }

.props-thumb {
  width: 100%; border-radius: 6px; display: block; margin-bottom: 10px; background: #111;
}

.set-active-btn {
  width: 100%; padding: 5px; border-radius: 6px; font-size: 11px;
  border: 1px solid rgba(108,99,255,0.3); background: rgba(108,99,255,0.06);
  color: rgba(108,99,255,0.8); cursor: pointer; transition: all 0.15s; margin-top: 4px;
}
.set-active-btn.on { background: rgba(108,99,255,0.2); color: #a78bfa; border-color: rgba(108,99,255,0.6); }
.set-active-btn:hover:not(.on) { background: rgba(108,99,255,0.12); color: #fff; }

.capture-btn {
  margin-top: auto; padding: 10px; border-radius: 9px; border: none;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  color: #fff; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 0.2s; flex-shrink: 0;
}
.capture-btn:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
.capture-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.zoom-overlay {
  position: fixed; inset: 0; z-index: 10000;
  background: rgba(0,0,0,0.85); display: flex;
  flex-direction: column; align-items: center; justify-content: center;
  cursor: pointer;
}
.zoom-img {
  max-width: 80vw; max-height: 80vh;
  border-radius: 10px; box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}
.zoom-hint {
  margin-top: 14px; font-size: 12px; color: rgba(255,255,255,0.3);
}

.fov-slider {
  flex: 1; height: 3px; accent-color: #6c63ff; cursor: pointer; min-width: 0;
}
.fov-num {
  width: 38px; flex-shrink: 0;
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; color: rgba(255,255,255,0.8); font-size: 10px;
  padding: 2px 4px; outline: none; text-align: center;
  -moz-appearance: textfield;
}
.fov-num::-webkit-outer-spin-button,
.fov-num::-webkit-inner-spin-button { -webkit-appearance: none; }

.bone-block {
  border-left: 2px solid rgba(108,99,255,0.2);
  padding-left: 6px; margin-bottom: 10px;
  cursor: pointer; border-radius: 0 4px 4px 0;
  transition: background 0.15s;
}
.bone-block:hover {
  background: rgba(108,99,255,0.08);
}
.bone-block.bone-selected {
  border-left-color: #ff4400;
  background: rgba(255,68,0,0.08);
}
.bone-hint {
  font-size: 9px; color: rgba(255,255,255,0.25); font-weight: 400;
}
.bone-name {
  font-size: 11px; color: rgba(255,255,255,0.6);
  margin-bottom: 4px; font-weight: 500;
}
.bone-row {
  display: flex; align-items: center; gap: 5px; margin-bottom: 3px;
}
.bone-axis {
  font-size: 10px; color: rgba(255,255,255,0.3);
  width: 26px; flex-shrink: 0; text-align: right;
}
.bone-slider {
  flex: 1; height: 3px; accent-color: #6c63ff; cursor: pointer; min-width: 0;
}
.bone-num {
  width: 38px; flex-shrink: 0;
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; color: rgba(255,255,255,0.8); font-size: 10px;
  padding: 2px 4px; outline: none; text-align: center;
  -moz-appearance: textfield;
}
.bone-num::-webkit-outer-spin-button,
.bone-num::-webkit-inner-spin-button { -webkit-appearance: none; }
</style>
