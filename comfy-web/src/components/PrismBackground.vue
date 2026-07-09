<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  height?: number
  baseWidth?: number
  animationType?: 'rotate' | 'hover' | '3drotate'
  glow?: number
  noise?: number
  scale?: number
  hueShift?: number
  colorFrequency?: number
  hoverStrength?: number
  inertia?: number
  bloom?: number
  timeScale?: number
}>(), {
  height: 3.4,
  baseWidth: 5.5,
  animationType: 'rotate',
  glow: 1,
  noise: 0,
  scale: 3.6,
  hueShift: 0,
  colorFrequency: 1,
  hoverStrength: 2,
  inertia: 0.05,
  bloom: 1,
  timeScale: 0.4,
})

const canvasRef = ref<HTMLCanvasElement>()
let animationFrame = 0
let resizeObserver: ResizeObserver | null = null
let cleanupEvents: (() => void) | null = null

const vertexShaderSource = `
attribute vec2 position;

void main() {
  gl_Position = vec4(position, 0.0, 1.0);
}
`

const fragmentShaderSource = `
precision highp float;

uniform vec2  iResolution;
uniform float iTime;
uniform float uHeight;
uniform mat3  uRot;
uniform int   uUseBaseWobble;
uniform float uGlow;
uniform float uNoise;
uniform float uSaturation;
uniform float uScale;
uniform float uHueShift;
uniform float uColorFreq;
uniform float uBloom;
uniform float uCenterShift;
uniform float uInvBaseHalf;
uniform float uInvHeight;
uniform float uMinAxis;
uniform float uPxScale;
uniform float uTimeScale;

vec4 tanh4(vec4 x) {
  vec4 e2x = exp(2.0 * x);
  return (e2x - 1.0) / (e2x + 1.0);
}

float rand(vec2 co) {
  return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453123);
}

float sdOctaAnisoInv(vec3 p) {
  vec3 q = vec3(abs(p.x) * uInvBaseHalf, abs(p.y) * uInvHeight, abs(p.z) * uInvBaseHalf);
  float m = q.x + q.y + q.z - 1.0;
  return m * uMinAxis * 0.5773502691896258;
}

float sdPyramidUpInv(vec3 p) {
  float oct = sdOctaAnisoInv(p);
  float halfSpace = -p.y;
  return max(oct, halfSpace);
}

mat3 hueRotation(float a) {
  float c = cos(a), s = sin(a);
  mat3 W = mat3(
    0.299, 0.587, 0.114,
    0.299, 0.587, 0.114,
    0.299, 0.587, 0.114
  );
  mat3 U = mat3(
     0.701, -0.587, -0.114,
    -0.299,  0.413, -0.114,
    -0.300, -0.588,  0.886
  );
  mat3 V = mat3(
     0.168, -0.331,  0.500,
     0.328,  0.035, -0.500,
    -0.497,  0.296,  0.201
  );
  return W + U * c + V * s;
}

void main() {
  vec2 f = (gl_FragCoord.xy - 0.5 * iResolution.xy) * uPxScale;
  float z = 5.0;
  float d = 0.0;
  vec3 p;
  vec4 o = vec4(0.0);

  mat2 wob = mat2(1.0);
  if (uUseBaseWobble == 1) {
    float t = iTime * uTimeScale;
    float c0 = cos(t + 0.0);
    float c1 = cos(t + 33.0);
    float c2 = cos(t + 11.0);
    wob = mat2(c0, c1, c2, c0);
  }

  const int STEPS = 100;
  for (int i = 0; i < STEPS; i++) {
    p = vec3(f, z);
    p.xz = p.xz * wob;
    p = uRot * p;
    vec3 q = p;
    q.y += uCenterShift;
    d = 0.1 + 0.2 * abs(sdPyramidUpInv(q));
    z -= d;
    o += (sin((p.y + z) * uColorFreq + vec4(0.0, 1.0, 2.0, 3.0)) + 1.0) / d;
  }

  o = tanh4(o * o * (uGlow * uBloom) / 1e5);

  vec3 col = o.rgb;
  float n = rand(gl_FragCoord.xy + vec2(iTime));
  col += (n - 0.5) * uNoise;
  col = clamp(col, 0.0, 1.0);

  float L = dot(col, vec3(0.2126, 0.7152, 0.0722));
  col = clamp(mix(vec3(L), col, uSaturation), 0.0, 1.0);

  if (abs(uHueShift) > 0.0001) {
    col = clamp(hueRotation(uHueShift) * col, 0.0, 1.0);
  }

  gl_FragColor = vec4(col, o.a);
}
`

function createShader(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)
  if (!shader) return null

  gl.shaderSource(shader, source)
  gl.compileShader(shader)

  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.error(gl.getShaderInfoLog(shader))
    gl.deleteShader(shader)
    return null
  }

  return shader
}

function createProgram(gl: WebGLRenderingContext) {
  const vertexShader = createShader(gl, gl.VERTEX_SHADER, vertexShaderSource)
  const fragmentShader = createShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource)
  if (!vertexShader || !fragmentShader) return null

  const program = gl.createProgram()
  if (!program) return null

  gl.attachShader(program, vertexShader)
  gl.attachShader(program, fragmentShader)
  gl.linkProgram(program)
  gl.deleteShader(vertexShader)
  gl.deleteShader(fragmentShader)

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error(gl.getProgramInfoLog(program))
    gl.deleteProgram(program)
    return null
  }

  return program
}

function setMat3FromEuler(yawY: number, pitchX: number, rollZ: number, out: Float32Array) {
  const cy = Math.cos(yawY)
  const sy = Math.sin(yawY)
  const cx = Math.cos(pitchX)
  const sx = Math.sin(pitchX)
  const cz = Math.cos(rollZ)
  const sz = Math.sin(rollZ)

  out[0] = cy * cz + sy * sx * sz
  out[1] = cx * sz
  out[2] = -sy * cz + cy * sx * sz
  out[3] = -cy * sz + sy * sx * cz
  out[4] = cx * cz
  out[5] = sy * sz + cy * sx * cz
  out[6] = sy * cx
  out[7] = -sx
  out[8] = cy * cx

  return out
}

onMounted(() => {
  const canvas = canvasRef.value
  const container = canvas?.parentElement
  if (!canvas || !container) return

  const gl = canvas.getContext('webgl', {
    alpha: true,
    antialias: false,
    depth: false,
    stencil: false,
    premultipliedAlpha: false,
  })
  if (!gl) return

  const program = createProgram(gl)
  if (!program) return

  const positionBuffer = gl.createBuffer()
  gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer)
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)

  const positionLocation = gl.getAttribLocation(program, 'position')
  const uniforms = {
    iResolution: gl.getUniformLocation(program, 'iResolution'),
    iTime: gl.getUniformLocation(program, 'iTime'),
    uHeight: gl.getUniformLocation(program, 'uHeight'),
    uRot: gl.getUniformLocation(program, 'uRot'),
    uUseBaseWobble: gl.getUniformLocation(program, 'uUseBaseWobble'),
    uGlow: gl.getUniformLocation(program, 'uGlow'),
    uNoise: gl.getUniformLocation(program, 'uNoise'),
    uSaturation: gl.getUniformLocation(program, 'uSaturation'),
    uScale: gl.getUniformLocation(program, 'uScale'),
    uHueShift: gl.getUniformLocation(program, 'uHueShift'),
    uColorFreq: gl.getUniformLocation(program, 'uColorFreq'),
    uBloom: gl.getUniformLocation(program, 'uBloom'),
    uCenterShift: gl.getUniformLocation(program, 'uCenterShift'),
    uInvBaseHalf: gl.getUniformLocation(program, 'uInvBaseHalf'),
    uInvHeight: gl.getUniformLocation(program, 'uInvHeight'),
    uMinAxis: gl.getUniformLocation(program, 'uMinAxis'),
    uPxScale: gl.getUniformLocation(program, 'uPxScale'),
    uTimeScale: gl.getUniformLocation(program, 'uTimeScale'),
  }

  const height = Math.max(0.001, props.height)
  const baseHalf = Math.max(0.001, props.baseWidth) * 0.5
  const scale = Math.max(0.001, props.scale)
  const timeScale = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : Math.max(0, props.timeScale)
  const rot = new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1])

  gl.useProgram(program)
  gl.disable(gl.DEPTH_TEST)
  gl.disable(gl.CULL_FACE)
  gl.clearColor(0, 0, 0, 0)
  gl.enableVertexAttribArray(positionLocation)
  gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0)

  gl.uniform1f(uniforms.uHeight, height)
  gl.uniform1f(uniforms.uGlow, Math.max(0, props.glow))
  gl.uniform1f(uniforms.uNoise, Math.max(0, props.noise))
  gl.uniform1f(uniforms.uSaturation, 1.5)
  gl.uniform1f(uniforms.uScale, scale)
  gl.uniform1f(uniforms.uHueShift, props.hueShift)
  gl.uniform1f(uniforms.uColorFreq, Math.max(0, props.colorFrequency))
  gl.uniform1f(uniforms.uBloom, Math.max(0, props.bloom))
  gl.uniform1f(uniforms.uCenterShift, height * 0.25)
  gl.uniform1f(uniforms.uInvBaseHalf, 1 / baseHalf)
  gl.uniform1f(uniforms.uInvHeight, 1 / height)
  gl.uniform1f(uniforms.uMinAxis, Math.min(baseHalf, height))
  gl.uniform1f(uniforms.uTimeScale, timeScale)
  gl.uniform1i(uniforms.uUseBaseWobble, props.animationType === 'rotate' ? 1 : 0)

  const resize = () => {
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const width = Math.max(1, container.clientWidth)
    const heightPx = Math.max(1, container.clientHeight)
    canvas.width = Math.floor(width * dpr)
    canvas.height = Math.floor(heightPx * dpr)
    gl.viewport(0, 0, canvas.width, canvas.height)
    gl.uniform2f(uniforms.iResolution, canvas.width, canvas.height)
    gl.uniform1f(uniforms.uPxScale, 1 / ((canvas.height || 1) * 0.1 * scale))
  }

  resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(container)
  resize()

  const startTime = performance.now()
  const random = () => Math.random()
  const wX = 0.3 + random() * 0.6
  const wY = 0.2 + random() * 0.7
  const wZ = 0.1 + random() * 0.5
  const phX = random() * Math.PI * 2
  const phZ = random() * Math.PI * 2
  const pointer = { x: 0, y: 0, inside: true }
  let yaw = 0
  let pitch = 0
  let roll = 0

  const onPointerMove = (event: PointerEvent) => {
    pointer.x = Math.max(-1, Math.min(1, (event.clientX - window.innerWidth * 0.5) / (window.innerWidth * 0.5)))
    pointer.y = Math.max(-1, Math.min(1, (event.clientY - window.innerHeight * 0.5) / (window.innerHeight * 0.5)))
    pointer.inside = true
  }
  const onLeave = () => {
    pointer.inside = false
  }

  if (props.animationType === 'hover') {
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    window.addEventListener('mouseleave', onLeave)
    window.addEventListener('blur', onLeave)
    cleanupEvents = () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('mouseleave', onLeave)
      window.removeEventListener('blur', onLeave)
    }
  }

  const render = (now: number) => {
    const time = (now - startTime) * 0.001

    if (props.animationType === 'hover') {
      const targetYaw = (pointer.inside ? -pointer.x : 0) * 0.6 * Math.max(0, props.hoverStrength)
      const targetPitch = (pointer.inside ? pointer.y : 0) * 0.6 * Math.max(0, props.hoverStrength)
      const inertia = Math.max(0, Math.min(1, props.inertia))
      yaw += (targetYaw - yaw) * inertia
      pitch += (targetPitch - pitch) * inertia
      roll += (0 - roll) * 0.1
      setMat3FromEuler(yaw, pitch, roll, rot)
    } else if (props.animationType === '3drotate') {
      const t = time * timeScale
      setMat3FromEuler(t * wY, Math.sin(t * wX + phX) * 0.6, Math.sin(t * wZ + phZ) * 0.5, rot)
    }

    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(uniforms.iTime, time)
    gl.uniformMatrix3fv(uniforms.uRot, false, rot)
    gl.drawArrays(gl.TRIANGLES, 0, 3)
    animationFrame = requestAnimationFrame(render)
  }

  animationFrame = requestAnimationFrame(render)
})

onUnmounted(() => {
  if (animationFrame) cancelAnimationFrame(animationFrame)
  if (resizeObserver) resizeObserver.disconnect()
  if (cleanupEvents) cleanupEvents()
})
</script>

<template>
  <div class="prism-container">
    <canvas ref="canvasRef" class="prism-canvas" />
  </div>
</template>

<style scoped>
.prism-container {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  pointer-events: none;
}

.prism-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
