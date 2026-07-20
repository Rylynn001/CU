<script setup lang="ts">
import { Camera, Mesh, Plane, Program, Renderer, Texture, Transform } from 'ogl'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type GL = Renderer['gl']
type GalleryItem = { image: string }

const props = withDefaults(defineProps<{
  items?: GalleryItem[]
  bend?: number
  borderRadius?: number
  scrollSpeed?: number
  scrollEase?: number
}>(), {
  bend: 0,
  borderRadius: 0.05,
  scrollSpeed: 3,
  scrollEase: 0.05,
})

const containerRef = ref<HTMLDivElement | null>(null)
let galleryApp: GalleryApp | undefined

const normalizedItems = computed(() => props.items || [])

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

function debounce<T extends (...args: never[]) => void>(func: T, wait: number) {
  let timeout = 0
  return (...args: Parameters<T>) => {
    window.clearTimeout(timeout)
    timeout = window.setTimeout(() => func(...args), wait)
  }
}

class Media {
  program!: Program
  plane!: Mesh
  scale = 1
  padding = 2
  width = 0
  x = 0
  speed = 0

  constructor(
    private readonly geometry: Plane,
    private readonly gl: GL,
    private readonly image: string,
    private readonly index: number,
    private readonly scene: Transform,
    private screen: { width: number; height: number },
    private viewport: { width: number; height: number },
    private readonly bend: number,
    private readonly borderRadius: number,
  ) {
    this.createShader()
    this.createMesh()
    this.onResize()
  }

  createShader() {
    // generateMipmaps 关闭：面板展示的是清晰静态图，mipmap 采样会让画面看起来发糊
    const texture = new Texture(this.gl, { generateMipmaps: false })
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
          p.z = (sin(p.x * 4.0 + uTime) * 0.8 + cos(p.y * 2.0 + uTime) * 0.8) * (0.08 + uSpeed * 0.35);
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

  update(scroll: { current: number; last: number }) {
    this.plane.position.x = this.x - scroll.current
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
  }

  onResize({ screen, viewport }: { screen?: { width: number; height: number }; viewport?: { width: number; height: number } } = {}) {
    if (screen) this.screen = screen
    if (viewport) this.viewport = viewport

    this.scale = this.screen.height / 1500
    this.plane.scale.y = (this.viewport.height * (900 * this.scale)) / this.screen.height
    this.plane.scale.x = (this.viewport.width * (700 * this.scale)) / this.screen.width
    this.plane.program.uniforms.uPlaneSizes.value = [this.plane.scale.x, this.plane.scale.y]
    this.width = this.plane.scale.x + this.padding
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
    private readonly config: Required<Omit<NonNullable<typeof props>, 'items'>> & { items: GalleryItem[] },
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
    // 有头有尾的直线排列：不做首尾拼接、不做循环 wraparound，滚到头/尾直接停住
    const galleryItems = this.config.items
    this.medias = galleryItems.map((item, index) => new Media(
      this.planeGeometry,
      this.gl,
      item.image,
      index,
      this.scene,
      this.screen,
      this.viewport,
      this.config.bend,
      this.config.borderRadius,
    ))
  }

  // 可滚动范围：[0, 最后一张图的 x 坐标]，超出范围直接夹住，不会绕回另一头
  getScrollBounds() {
    if (this.medias.length === 0) return { min: 0, max: 0 }
    return { min: 0, max: this.medias[this.medias.length - 1].x }
  }

  clampScroll() {
    const { min, max } = this.getScrollBounds()
    this.scroll.target = Math.min(Math.max(this.scroll.target, min), max)
  }

  onWheel(e: WheelEvent) {
    e.preventDefault()
    const delta = e.deltaY || e.deltaX || e.detail
    this.scroll.target += (delta > 0 ? this.config.scrollSpeed : -this.config.scrollSpeed) * 0.6
    this.clampScroll()
    this.onCheckDebounce()
  }

  onKeyDown(e: KeyboardEvent) {
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      this.scroll.target += this.config.scrollSpeed * 5
      this.clampScroll()
      this.onCheckDebounce()
    }
    if (e.key === 'ArrowLeft') {
      e.preventDefault()
      this.scroll.target -= this.config.scrollSpeed * 5
      this.clampScroll()
      this.onCheckDebounce()
    }
  }

  onCheck() {
    if (!this.medias[0]) return
    const width = this.medias[0].width
    const itemIndex = Math.round(this.scroll.target / width)
    this.scroll.target = width * itemIndex
    this.clampScroll()
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
    this.medias.forEach((media) => media.update(this.scroll))
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

function mountGallery() {
  const container = containerRef.value
  if (!container) return

  galleryApp?.destroy()
  galleryApp = new GalleryApp(container, {
    items: normalizedItems.value,
    bend: props.bend,
    borderRadius: props.borderRadius,
    scrollSpeed: props.scrollSpeed,
    scrollEase: props.scrollEase,
  })
}

watch(
  () => [normalizedItems.value, props.bend, props.borderRadius, props.scrollSpeed, props.scrollEase],
  () => {
    mountGallery()
  },
  { deep: true },
)

onMounted(() => {
  mountGallery()
})

onBeforeUnmount(() => {
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
