<script setup lang="ts">
import { Camera, Mesh, Plane, Program, Renderer, Texture, Transform } from 'ogl'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type GL = Renderer['gl']
type GalleryItem = { image: string; text: string }
type Direction = 'right' | 'left'

const props = withDefaults(defineProps<{
  items?: GalleryItem[]
  bend?: number
  textColor?: string
  borderRadius?: number
  font?: string
  fontUrl?: string
  scrollSpeed?: number
  scrollEase?: number
}>(), {
  bend: 0,
  textColor: '#ffffff',
  borderRadius: 0.05,
  font: 'bold 30px Orbitron',
  fontUrl: '',
  scrollSpeed: 3,
  scrollEase: 0.05,
})

const containerRef = ref<HTMLDivElement | null>(null)
let galleryApp: GalleryApp | undefined
let mountToken = 0

const normalizedItems = computed(() => props.items || [])

function debounce<T extends (...args: never[]) => void>(func: T, wait: number) {
  let timeout = 0
  return (...args: Parameters<T>) => {
    window.clearTimeout(timeout)
    timeout = window.setTimeout(() => func(...args), wait)
  }
}

function lerp(p1: number, p2: number, t: number) {
  return p1 + (p2 - p1) * t
}

function autoBind(instance: object) {
  const proto = Object.getPrototypeOf(instance)
  Object.getOwnPropertyNames(proto).forEach((key) => {
    const item = (instance as Record<string, unknown>)[key]
    if (key !== 'constructor' && typeof item === 'function') {
      ;(instance as Record<string, unknown>)[key] = item.bind(instance)
    }
  })
}

function getFontSize(font: string) {
  const match = font.match(/(\d+)px/)
  return match ? Number.parseInt(match[1], 10) : 30
}

function createTextTexture(gl: GL, text: string, font: string, color: string) {
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')
  if (!context) throw new Error('无法创建文字画布')

  context.font = font
  const metrics = context.measureText(text)
  const textWidth = Math.ceil(metrics.width)
  const textHeight = Math.ceil(getFontSize(font) * 1.2)

  canvas.width = textWidth + 20
  canvas.height = textHeight + 20

  context.font = font
  context.fillStyle = color
  context.textBaseline = 'middle'
  context.textAlign = 'center'
  context.clearRect(0, 0, canvas.width, canvas.height)
  context.fillText(text, canvas.width / 2, canvas.height / 2)

  const texture = new Texture(gl, { generateMipmaps: false })
  texture.image = canvas
  return { texture, width: canvas.width, height: canvas.height }
}

async function loadFontFromFile(url: string) {
  const fileName = (url.split('/').pop() || 'custom-font').split('?')[0]
  const family = fileName.replace(/\.(woff2?|ttf|otf|eot)$/i, '').replace(/[^a-zA-Z0-9-_ ]/g, '').trim() || 'CircularGalleryFont'
  const fontFace = new FontFace(family, `url(${url})`)
  await fontFace.load()
  document.fonts.add(fontFace)
  return family
}

async function loadFontFromStylesheet(url: string) {
  const response = await fetch(url)
  if (!response.ok) throw new Error('字体样式加载失败')
  const cssText = await response.text()
  const faceBlocks = cssText.match(/@font-face\s*{[^}]*}/g) || []
  let family = ''
  const fontFaces: FontFace[] = []

  faceBlocks.forEach((block) => {
    const familyMatch = block.match(/font-family:\s*['"]?([^;'"]+)['"]?/)
    const urlMatch = block.match(/url\(\s*['"]?([^'")]+)['"]?\s*\)/)
    if (!familyMatch || !urlMatch) return

    family = familyMatch[1].trim()
    const descriptors: FontFaceDescriptors = {}
    const weightMatch = block.match(/font-weight:\s*([^;]+);/)
    const styleMatch = block.match(/font-style:\s*([^;]+);/)
    const rangeMatch = block.match(/unicode-range:\s*([^;]+);/)
    if (weightMatch) descriptors.weight = weightMatch[1].trim()
    if (styleMatch) descriptors.style = styleMatch[1].trim()
    if (rangeMatch) descriptors.unicodeRange = rangeMatch[1].trim()
    fontFaces.push(new FontFace(family, `url(${urlMatch[1]})`, descriptors))
  })

  if (!family) throw new Error('未找到可用字体')
  await Promise.allSettled(fontFaces.map(async (face) => {
    await face.load()
    document.fonts.add(face)
  }))
  return family
}

async function resolveFont(font: string, fontUrl: string) {
  if (!fontUrl) {
    try {
      await document.fonts.load(font)
      await document.fonts.ready
    } catch {
      // 浏览器会自动回退到可用字体。
    }
    return font
  }

  try {
    const isStylesheet = fontUrl.includes('fonts.googleapis.com') || /\.css(\?.*)?$/i.test(fontUrl)
    const family = isStylesheet ? await loadFontFromStylesheet(fontUrl) : await loadFontFromFile(fontUrl)
    const sizeMatch = font.match(/^\s*(.*?\d+px)/)
    return `${sizeMatch ? sizeMatch[1].trim() : 'bold 30px'} "${family}"`
  } catch {
    return font
  }
}

class Title {
  mesh!: Mesh

  constructor(
    private readonly gl: GL,
    private readonly plane: Mesh,
    private readonly text: string,
    private readonly textColor: string,
    private readonly font: string,
  ) {
    this.createMesh()
  }

  createMesh() {
    const { texture, width, height } = createTextTexture(this.gl, this.text, this.font, this.textColor)
    const geometry = new Plane(this.gl)
    const program = new Program(this.gl, {
      vertex: `
        attribute vec3 position;
        attribute vec2 uv;
        uniform mat4 modelViewMatrix;
        uniform mat4 projectionMatrix;
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragment: `
        precision highp float;
        uniform sampler2D tMap;
        varying vec2 vUv;
        void main() {
          vec4 color = texture2D(tMap, vUv);
          if (color.a < 0.1) discard;
          gl_FragColor = color;
        }
      `,
      uniforms: { tMap: { value: texture } },
      transparent: true,
    })
    this.mesh = new Mesh(this.gl, { geometry, program })
    const aspect = width / height
    const textHeightScaled = this.plane.scale.y * 0.15
    this.mesh.scale.set(textHeightScaled * aspect, textHeightScaled, 1)
    this.mesh.position.y = -this.plane.scale.y * 0.5 - textHeightScaled * 0.5 - 0.05
    this.mesh.setParent(this.plane)
  }
}

class Media {
  extra = 0
  program!: Program
  plane!: Mesh
  scale = 1
  padding = 2
  width = 0
  widthTotal = 0
  x = 0
  speed = 0

  constructor(
    private readonly geometry: Plane,
    private readonly gl: GL,
    private readonly image: string,
    private readonly index: number,
    private readonly length: number,
    private readonly scene: Transform,
    private screen: { width: number; height: number },
    private readonly text: string,
    private viewport: { width: number; height: number },
    private readonly bend: number,
    private readonly textColor: string,
    private readonly borderRadius: number,
    private readonly font: string,
  ) {
    this.createShader()
    this.createMesh()
    new Title(this.gl, this.plane, this.text, this.textColor, this.font)
    this.onResize()
  }

  createShader() {
    const texture = new Texture(this.gl, { generateMipmaps: true })
    this.program = new Program(this.gl, {
      depthTest: false,
      depthWrite: false,
      vertex: `
        precision highp float;
        attribute vec3 position;
        attribute vec2 uv;
        uniform mat4 modelViewMatrix;
        uniform mat4 projectionMatrix;
        uniform float uTime;
        uniform float uSpeed;
        varying vec2 vUv;
        void main() {
          vUv = uv;
          vec3 p = position;
          p.z = (sin(p.x * 4.0 + uTime) * 1.5 + cos(p.y * 2.0 + uTime) * 1.5) * (0.1 + uSpeed * 0.5);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
        }
      `,
      fragment: `
        precision highp float;
        uniform vec2 uImageSizes;
        uniform vec2 uPlaneSizes;
        uniform sampler2D tMap;
        uniform float uBorderRadius;
        varying vec2 vUv;

        float roundedBoxSDF(vec2 p, vec2 b, float r) {
          vec2 d = abs(p) - b;
          return length(max(d, vec2(0.0))) + min(max(d.x, d.y), 0.0) - r;
        }

        void main() {
          vec2 ratio = vec2(
            min((uPlaneSizes.x / uPlaneSizes.y) / (uImageSizes.x / uImageSizes.y), 1.0),
            min((uPlaneSizes.y / uPlaneSizes.x) / (uImageSizes.y / uImageSizes.x), 1.0)
          );
          vec2 uv = vec2(
            vUv.x * ratio.x + (1.0 - ratio.x) * 0.5,
            vUv.y * ratio.y + (1.0 - ratio.y) * 0.5
          );
          vec4 color = texture2D(tMap, uv);
          float d = roundedBoxSDF(vUv - 0.5, vec2(0.5 - uBorderRadius), uBorderRadius);
          float alpha = 1.0 - smoothstep(-0.002, 0.002, d);
          gl_FragColor = vec4(color.rgb, alpha);
        }
      `,
      uniforms: {
        tMap: { value: texture },
        uPlaneSizes: { value: [0, 0] },
        uImageSizes: { value: [1, 1] },
        uSpeed: { value: 0 },
        uTime: { value: 100 * Math.random() },
        uBorderRadius: { value: this.borderRadius },
      },
      transparent: true,
    })

    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = this.image
    img.onload = () => {
      texture.image = img
      this.program.uniforms.uImageSizes.value = [img.naturalWidth, img.naturalHeight]
    }
  }

  createMesh() {
    this.plane = new Mesh(this.gl, {
      geometry: this.geometry,
      program: this.program,
    })
    this.plane.setParent(this.scene)
  }

  update(scroll: { current: number; last: number }, direction: Direction) {
    this.plane.position.x = this.x - scroll.current - this.extra
    const x = this.plane.position.x
    const halfWidth = this.viewport.width / 2

    if (this.bend === 0) {
      this.plane.position.y = 0
      this.plane.rotation.z = 0
    } else {
      const bendAbs = Math.abs(this.bend)
      const radius = (halfWidth * halfWidth + bendAbs * bendAbs) / (2 * bendAbs)
      const effectiveX = Math.min(Math.abs(x), halfWidth)
      const arc = radius - Math.sqrt(radius * radius - effectiveX * effectiveX)
      this.plane.position.y = this.bend > 0 ? -arc : arc
      this.plane.rotation.z = (this.bend > 0 ? -1 : 1) * Math.sign(x) * Math.asin(effectiveX / radius)
    }

    this.speed = scroll.current - scroll.last
    this.program.uniforms.uTime.value += 0.04
    this.program.uniforms.uSpeed.value = this.speed

    const planeOffset = this.plane.scale.x / 2
    const viewportOffset = this.viewport.width / 2
    const isBefore = this.plane.position.x + planeOffset < -viewportOffset
    const isAfter = this.plane.position.x - planeOffset > viewportOffset
    if (direction === 'right' && isBefore) this.extra -= this.widthTotal
    if (direction === 'left' && isAfter) this.extra += this.widthTotal
  }

  onResize({ screen, viewport }: { screen?: { width: number; height: number }; viewport?: { width: number; height: number } } = {}) {
    if (screen) this.screen = screen
    if (viewport) this.viewport = viewport

    this.scale = this.screen.height / 1500
    this.plane.scale.y = (this.viewport.height * (900 * this.scale)) / this.screen.height
    this.plane.scale.x = (this.viewport.width * (700 * this.scale)) / this.screen.width
    this.plane.program.uniforms.uPlaneSizes.value = [this.plane.scale.x, this.plane.scale.y]
    this.width = this.plane.scale.x + this.padding
    this.widthTotal = this.width * this.length
    this.x = this.width * this.index
  }
}

class GalleryApp {
  scroll: { ease: number; current: number; target: number; last: number; position?: number }
  renderer!: Renderer
  gl!: GL
  camera!: Camera
  scene!: Transform
  planeGeometry!: Plane
  medias: Media[] = []
  screen = { width: 1, height: 1 }
  viewport = { width: 1, height: 1 }
  raf = 0
  onCheckDebounce: () => void

  constructor(
    private readonly container: HTMLElement,
    private readonly config: Required<Omit<NonNullable<typeof props>, 'items' | 'fontUrl'>> & { items: GalleryItem[] },
  ) {
    autoBind(this)
    this.scroll = { ease: config.scrollEase, current: 0, target: 0, last: 0 }
    this.onCheckDebounce = debounce(this.onCheck, 200)
    this.createRenderer()
    this.createCamera()
    this.createScene()
    this.onResize()
    this.createGeometry()
    this.createMedias()
    this.update()
    this.addEventListeners()
  }

  createRenderer() {
    this.renderer = new Renderer({
      alpha: true,
      antialias: true,
      dpr: Math.min(window.devicePixelRatio || 1, 2),
    })
    this.gl = this.renderer.gl
    this.gl.clearColor(0, 0, 0, 0)
    this.container.appendChild(this.renderer.gl.canvas)
  }

  createCamera() {
    this.camera = new Camera(this.gl)
    this.camera.fov = 45
    this.camera.position.z = 20
  }

  createScene() {
    this.scene = new Transform()
  }

  createGeometry() {
    this.planeGeometry = new Plane(this.gl, {
      heightSegments: 50,
      widthSegments: 100,
    })
  }

  createMedias() {
    const galleryItems = this.config.items
    const mediasImages = galleryItems.length ? galleryItems.concat(galleryItems) : []
    this.medias = mediasImages.map((item, index) => new Media(
      this.planeGeometry,
      this.gl,
      item.image,
      index,
      mediasImages.length,
      this.scene,
      this.screen,
      item.text,
      this.viewport,
      this.config.bend,
      this.config.textColor,
      this.config.borderRadius,
      this.config.font,
    ))
  }

  onWheel(e: WheelEvent) {
    e.preventDefault()
    const delta = e.deltaY || e.deltaX || e.detail
    this.scroll.target += (delta > 0 ? this.config.scrollSpeed : -this.config.scrollSpeed) * 0.2
    this.onCheckDebounce()
  }

  onKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      this.scroll.target += this.config.scrollSpeed * 5
      this.onCheckDebounce()
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      this.scroll.target -= this.config.scrollSpeed * 5
      this.onCheckDebounce()
    }
  }

  onCheck() {
    if (!this.medias[0]) return
    const width = this.medias[0].width
    const itemIndex = Math.round(Math.abs(this.scroll.target) / width)
    const item = width * itemIndex
    this.scroll.target = this.scroll.target < 0 ? -item : item
  }

  onResize() {
    this.screen = {
      width: Math.max(this.container.clientWidth, 1),
      height: Math.max(this.container.clientHeight, 1),
    }
    this.renderer.setSize(this.screen.width, this.screen.height)
    this.camera.perspective({ aspect: this.screen.width / this.screen.height })
    const fov = (this.camera.fov * Math.PI) / 180
    const height = 2 * Math.tan(fov / 2) * this.camera.position.z
    this.viewport = { width: height * this.camera.aspect, height }
    this.medias.forEach((media) => media.onResize({ screen: this.screen, viewport: this.viewport }))
  }

  update() {
    this.scroll.current = lerp(this.scroll.current, this.scroll.target, this.scroll.ease)
    const direction: Direction = this.scroll.current > this.scroll.last ? 'right' : 'left'
    this.medias.forEach((media) => media.update(this.scroll, direction))
    this.renderer.render({ scene: this.scene, camera: this.camera })
    this.scroll.last = this.scroll.current
    this.raf = window.requestAnimationFrame(this.update)
  }

  addEventListeners() {
    window.addEventListener('resize', this.onResize)
    this.container.addEventListener('wheel', this.onWheel)
    this.container.addEventListener('keydown', this.onKeyDown)
  }

  destroy() {
    window.cancelAnimationFrame(this.raf)
    window.removeEventListener('resize', this.onResize)
    this.container.removeEventListener('wheel', this.onWheel)
    this.container.removeEventListener('keydown', this.onKeyDown)
    this.renderer.gl.canvas.remove()
  }
}

async function mountGallery() {
  const container = containerRef.value
  if (!container) return

  const currentToken = ++mountToken
  galleryApp?.destroy()
  galleryApp = undefined

  const font = await resolveFont(props.font, props.fontUrl)
  if (currentToken !== mountToken || !containerRef.value) return

  galleryApp = new GalleryApp(container, {
    items: normalizedItems.value,
    bend: props.bend,
    textColor: props.textColor,
    borderRadius: props.borderRadius,
    font,
    scrollSpeed: props.scrollSpeed,
    scrollEase: props.scrollEase,
  })
}

watch(
  () => [normalizedItems.value, props.bend, props.textColor, props.borderRadius, props.font, props.fontUrl, props.scrollSpeed, props.scrollEase],
  () => {
    mountGallery()
  },
  { deep: true },
)

onMounted(() => {
  mountGallery()
})

onBeforeUnmount(() => {
  mountToken += 1
  galleryApp?.destroy()
})
</script>

<template>
  <div
    ref="containerRef"
    class="circular-gallery"
    tabindex="0"
    role="region"
    aria-label="循环资产画廊"
  />
</template>

<style scoped>
.circular-gallery {
  width: 100%;
  height: 100%;
  overflow: hidden;
  cursor: default;
}

.circular-gallery:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 4px;
}
</style>
