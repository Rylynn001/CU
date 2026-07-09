<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

type RaysOrigin =
  | 'top-center'
  | 'top-left'
  | 'top-right'
  | 'right'
  | 'left'
  | 'bottom-center'
  | 'bottom-right'
  | 'bottom-left'

const props = withDefaults(defineProps<{
  raysOrigin?: RaysOrigin
  raysColor?: string
  raysSpeed?: number
  lightSpread?: number
  rayLength?: number
  pulsating?: boolean
  fadeDistance?: number
  saturation?: number
  followMouse?: boolean
  mouseInfluence?: number
  noiseAmount?: number
  distortion?: number
}>(), {
  raysOrigin: 'top-center',
  raysColor: '#ffffff',
  raysSpeed: 1,
  lightSpread: 1,
  rayLength: 2,
  pulsating: false,
  fadeDistance: 1,
  saturation: 1,
  followMouse: true,
  mouseInfluence: 0.1,
  noiseAmount: 0,
  distortion: 0,
})

const canvasRef = ref<HTMLCanvasElement>()
let animationFrame = 0
let resizeObserver: ResizeObserver | null = null
let gl: WebGLRenderingContext | null = null
let program: WebGLProgram | null = null
let startTime = 0
let cleanupMouseMove: (() => void) | null = null
const mouse = { x: 0.5, y: 0.5 }
const smoothMouse = { x: 0.5, y: 0.5 }

const vertexShaderSource = `
attribute vec2 position;

void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`

const fragmentShaderSource = `
precision highp float;

uniform float iTime;
uniform vec2  iResolution;
uniform vec2  rayPos;
uniform vec2  rayDir;
uniform vec3  raysColor;
uniform float raysSpeed;
uniform float lightSpread;
uniform float rayLength;
uniform float pulsating;
uniform float fadeDistance;
uniform float saturation;
uniform vec2  mousePos;
uniform float mouseInfluence;
uniform float noiseAmount;
uniform float distortion;

float noise(vec2 st) {
  return fract(sin(dot(st.xy, vec2(12.9898,78.233))) * 43758.5453123);
}

float rayStrength(vec2 raySource, vec2 rayRefDirection, vec2 coord,
                  float seedA, float seedB, float speed) {
  vec2 sourceToCoord = coord - raySource;
  vec2 dirNorm = normalize(sourceToCoord);
  float cosAngle = dot(dirNorm, rayRefDirection);
  float distortedAngle = cosAngle + distortion * sin(iTime * 2.0 + length(sourceToCoord) * 0.01) * 0.2;
  float spreadFactor = pow(max(distortedAngle, 0.0), 1.0 / max(lightSpread, 0.001));
  float distance = length(sourceToCoord);
  float maxDistance = iResolution.x * rayLength;
  float lengthFalloff = clamp((maxDistance - distance) / maxDistance, 0.0, 1.0);
  float fadeFalloff = clamp((iResolution.x * fadeDistance - distance) / (iResolution.x * fadeDistance), 0.5, 1.0);
  float pulse = pulsating > 0.5 ? (0.8 + 0.2 * sin(iTime * speed * 3.0)) : 1.0;

  float baseStrength = clamp(
    (0.45 + 0.15 * sin(distortedAngle * seedA + iTime * speed)) +
    (0.3 + 0.2 * cos(-distortedAngle * seedB + iTime * speed)),
    0.0, 1.0
  );

  return baseStrength * lengthFalloff * fadeFalloff * spreadFactor * pulse;
}

void main() {
  vec2 coord = vec2(gl_FragCoord.x, iResolution.y - gl_FragCoord.y);
  vec2 finalRayDir = rayDir;

  if (mouseInfluence > 0.0) {
    vec2 mouseScreenPos = mousePos * iResolution.xy;
    vec2 mouseDirection = normalize(mouseScreenPos - rayPos);
    finalRayDir = normalize(mix(rayDir, mouseDirection, mouseInfluence));
  }

  vec4 rays1 = vec4(1.0) * rayStrength(rayPos, finalRayDir, coord, 36.2214, 21.11349, 1.5 * raysSpeed);
  vec4 rays2 = vec4(1.0) * rayStrength(rayPos, finalRayDir, coord, 22.3991, 18.0234, 1.1 * raysSpeed);
  vec4 fragColor = rays1 * 0.5 + rays2 * 0.4;

  if (noiseAmount > 0.0) {
    float n = noise(coord * 0.01 + iTime * 0.1);
    fragColor.rgb *= (1.0 - noiseAmount + noiseAmount * n);
  }

  float brightness = 1.0 - (coord.y / iResolution.y);
  fragColor.x *= 0.1 + brightness * 0.8;
  fragColor.y *= 0.3 + brightness * 0.6;
  fragColor.z *= 0.5 + brightness * 0.5;

  if (saturation != 1.0) {
    float gray = dot(fragColor.rgb, vec3(0.299, 0.587, 0.114));
    fragColor.rgb = mix(vec3(gray), fragColor.rgb, saturation);
  }

  fragColor.rgb *= raysColor;
  gl_FragColor = fragColor;
}
`

function hexToRgb(hex: string): [number, number, number] {
  const match = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!match) return [1, 1, 1]

  return [
    parseInt(match[1], 16) / 255,
    parseInt(match[2], 16) / 255,
    parseInt(match[3], 16) / 255,
  ]
}

function getAnchorAndDir(origin: RaysOrigin, width: number, height: number) {
  const outside = 0.2

  switch (origin) {
    case 'top-left':
      return { anchor: [0, -outside * height], dir: [0, 1] }
    case 'top-right':
      return { anchor: [width, -outside * height], dir: [0, 1] }
    case 'left':
      return { anchor: [-outside * width, 0.5 * height], dir: [1, 0] }
    case 'right':
      return { anchor: [(1 + outside) * width, 0.5 * height], dir: [-1, 0] }
    case 'bottom-left':
      return { anchor: [0, (1 + outside) * height], dir: [0, -1] }
    case 'bottom-center':
      return { anchor: [0.5 * width, (1 + outside) * height], dir: [0, -1] }
    case 'bottom-right':
      return { anchor: [width, (1 + outside) * height], dir: [0, -1] }
    default:
      return { anchor: [0.5 * width, -outside * height], dir: [0, 1] }
  }
}

function createShader(context: WebGLRenderingContext, type: number, source: string) {
  const shader = context.createShader(type)
  if (!shader) return null

  context.shaderSource(shader, source)
  context.compileShader(shader)

  if (!context.getShaderParameter(shader, context.COMPILE_STATUS)) {
    console.error(context.getShaderInfoLog(shader))
    context.deleteShader(shader)
    return null
  }

  return shader
}

function createProgram(context: WebGLRenderingContext) {
  const vertexShader = createShader(context, context.VERTEX_SHADER, vertexShaderSource)
  const fragmentShader = createShader(context, context.FRAGMENT_SHADER, fragmentShaderSource)
  if (!vertexShader || !fragmentShader) return null

  const createdProgram = context.createProgram()
  if (!createdProgram) return null

  context.attachShader(createdProgram, vertexShader)
  context.attachShader(createdProgram, fragmentShader)
  context.linkProgram(createdProgram)
  context.deleteShader(vertexShader)
  context.deleteShader(fragmentShader)

  if (!context.getProgramParameter(createdProgram, context.LINK_STATUS)) {
    console.error(context.getProgramInfoLog(createdProgram))
    context.deleteProgram(createdProgram)
    return null
  }

  return createdProgram
}

onMounted(() => {
  const canvas = canvasRef.value
  const container = canvas?.parentElement
  if (!canvas || !container) return

  gl = canvas.getContext('webgl', {
    alpha: true,
    antialias: false,
    depth: false,
    stencil: false,
    premultipliedAlpha: false,
  })
  if (!gl) return

  program = createProgram(gl)
  if (!program) return

  const positionBuffer = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)

  const positionLocation = gl.getAttribLocation(program, 'position')
  const uniforms = {
    iTime: gl.getUniformLocation(program, 'iTime'),
    iResolution: gl.getUniformLocation(program, 'iResolution'),
    rayPos: gl.getUniformLocation(program, 'rayPos'),
    rayDir: gl.getUniformLocation(program, 'rayDir'),
    raysColor: gl.getUniformLocation(program, 'raysColor'),
    raysSpeed: gl.getUniformLocation(program, 'raysSpeed'),
    lightSpread: gl.getUniformLocation(program, 'lightSpread'),
    rayLength: gl.getUniformLocation(program, 'rayLength'),
    pulsating: gl.getUniformLocation(program, 'pulsating'),
    fadeDistance: gl.getUniformLocation(program, 'fadeDistance'),
    saturation: gl.getUniformLocation(program, 'saturation'),
    mousePos: gl.getUniformLocation(program, 'mousePos'),
    mouseInfluence: gl.getUniformLocation(program, 'mouseInfluence'),
    noiseAmount: gl.getUniformLocation(program, 'noiseAmount'),
    distortion: gl.getUniformLocation(program, 'distortion'),
  }

  gl.useProgram(program)
  gl.disable(gl.DEPTH_TEST)
  gl.disable(gl.CULL_FACE)
  gl.clearColor(0, 0, 0, 0)
  gl.enableVertexAttribArray(positionLocation)
  gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)

  const [r, g, b] = hexToRgb(props.raysColor)
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  gl.uniform3f(uniforms.raysColor, r, g, b)
  gl.uniform1f(uniforms.raysSpeed, reducedMotion ? 0 : props.raysSpeed)
  gl.uniform1f(uniforms.lightSpread, props.lightSpread)
  gl.uniform1f(uniforms.rayLength, props.rayLength)
  gl.uniform1f(uniforms.pulsating, props.pulsating ? 1 : 0)
  gl.uniform1f(uniforms.fadeDistance, props.fadeDistance)
  gl.uniform1f(uniforms.saturation, props.saturation)
  gl.uniform1f(uniforms.mouseInfluence, props.followMouse ? props.mouseInfluence : 0)
  gl.uniform1f(uniforms.noiseAmount, props.noiseAmount)
  gl.uniform1f(uniforms.distortion, props.distortion)

  const resize = () => {
    if (!gl) return

    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const width = Math.max(1, container.clientWidth)
    const height = Math.max(1, container.clientHeight)
    canvas.width = Math.floor(width * dpr)
    canvas.height = Math.floor(height * dpr)
    gl.viewport(0, 0, canvas.width, canvas.height)
    gl.uniform2f(uniforms.iResolution, canvas.width, canvas.height)

    const { anchor, dir } = getAnchorAndDir(props.raysOrigin, canvas.width, canvas.height)
    gl.uniform2f(uniforms.rayPos, anchor[0], anchor[1])
    gl.uniform2f(uniforms.rayDir, dir[0], dir[1])
  }

  const handleMouseMove = (event: MouseEvent) => {
    const rect = container.getBoundingClientRect()
    mouse.x = (event.clientX - rect.left) / rect.width
    mouse.y = (event.clientY - rect.top) / rect.height
  }

  if (props.followMouse) {
    window.addEventListener('mousemove', handleMouseMove, { passive: true })
    cleanupMouseMove = () => window.removeEventListener('mousemove', handleMouseMove)
  }

  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(container)
  resize()

  startTime = performance.now()
  const render = (now: number) => {
    if (!gl) return

    const smoothing = 0.92
    smoothMouse.x = smoothMouse.x * smoothing + mouse.x * (1 - smoothing)
    smoothMouse.y = smoothMouse.y * smoothing + mouse.y * (1 - smoothing)

    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(uniforms.iTime, (now - startTime) * 0.001)
    gl.uniform2f(uniforms.mousePos, smoothMouse.x, smoothMouse.y)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
    animationFrame = requestAnimationFrame(render)
  }

  animationFrame = requestAnimationFrame(render)
})

onUnmounted(() => {
  if (animationFrame) cancelAnimationFrame(animationFrame)
  if (resizeObserver) resizeObserver.disconnect()
  if (cleanupMouseMove) cleanupMouseMove()
  if (gl && program) gl.deleteProgram(program)
})
</script>

<template>
  <div class="light-rays-container">
    <canvas ref="canvasRef" class="light-rays-canvas" />
  </div>
</template>

<style scoped>
.light-rays-container {
  width: 100%;
  height: 100%;
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.light-rays-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
