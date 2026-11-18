import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import { computed, markRaw, reactive, ref } from 'vue'
import { makeNode, nodeKinds, validConnection } from '../src/services/canvasGraph.ts'
import { normalizeAspectRatioParameters } from '../src/constants/aspectRatios.ts'

// 直接执行组件的脚本，隔离接口和挂载副作用，避免把处理逻辑复制到测试里。
function loadSetup(path, bindings, names) {
  const { descriptor } = parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const script = ts.createSourceFile(path, descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const source = script.statements.filter(statement => !ts.isImportDeclaration(statement)).map(statement => statement.getText(script)).join('\n')
  const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } })
  return new Function(...Object.keys(bindings), `${outputText}\nreturn { ${names.join(', ')} }`)(...Object.values(bindings))
}

function canvasSetup() {
  const flow = { connectionStatus: ref(null), screenToFlowCoordinate: point => point }
  const pane = { closest: selector => selector === '.vue-flow__pane' ? pane : null }
  const window = { document: {
    elementFromPoint: () => pane,
    querySelector: () => ({ getBoundingClientRect: () => ({ left: 0, top: 0, width: 1000, height: 800 }) }),
  } }
  const noop = () => {}
  const setup = loadSetup('../src/views/Canvas.vue', {
    computed, markRaw, reactive, ref, makeNode, nodeKinds, validConnection, window, normalizeAspectRatioParameters,
    useVueFlow: () => flow, CanvasNodeComponent: {}, canvasActionsKey: Symbol(),
    useRouter: () => ({}),
    subscribeCanvasTasks: () => () => {},
    watch: noop, provide: noop, onMounted: noop, onBeforeUnmount: noop, onBeforeRouteLeave: noop,
  }, ['connectStart', 'connectEnd', 'connect', 'paneClick', 'connectionCandidates', 'addConnectedNode', 'connectionMenu', 'pendingConnection', 'nodes', 'edges', 'ready', 'syncModelParameters'])
  setup.ready.value = true
  setup.nodes.value.push(makeNode('remote-imageGenerationNode', { x: 0, y: 0 }))
  return { ...setup, flow, window }
}

test('拖线在空白处松手不报错，松手后仍可选择兼容节点并自动连接', () => {
  const canvas = canvasSetup()
  const source = canvas.nodes.value[0]
  canvas.connectStart({ nodeId: source.id, handleId: 'image', handleType: 'source' })
  assert.doesNotThrow(() => canvas.connectEnd({ type: 'mouseup', clientX: 500, clientY: 200 }))
  assert.equal(canvas.pendingConnection.value, undefined)
  assert.ok(canvas.connectionMenu.value)
  canvas.paneClick()
  assert.ok(canvas.connectionMenu.value, '松手产生的点击不应关闭菜单')
  assert.ok(canvas.connectionCandidates().some(kind => kind.type === 'remote-videoGenerationNode'))
  canvas.addConnectedNode('remote-videoGenerationNode')
  assert.equal(canvas.nodes.value.length, 2)
  assert.equal(canvas.edges.value.length, 1)
  assert.equal(canvas.edges.value[0].source, source.id)
  assert.equal(canvas.connectionMenu.value, undefined)
})

test('成功连接、无效位置松手及取消触摸均清理起始状态，不打开创建菜单', () => {
  for (const state of ['valid', 'outside', 'touchcancel']) {
    const canvas = canvasSetup()
    const source = canvas.nodes.value[0]
    canvas.connectStart({ nodeId: source.id, handleId: 'image', handleType: 'source' })
    if (state === 'valid') canvas.flow.connectionStatus.value = 'valid'
    if (state === 'outside') canvas.window.document.elementFromPoint = () => null
    canvas.connectEnd({ type: state === 'touchcancel' ? state : 'mouseup', clientX: 500, clientY: 200 })
    assert.equal(canvas.pendingConnection.value, undefined)
    assert.equal(canvas.connectionMenu.value, undefined)
  }
})

test('画布历史和模型切换保留所选比例，清理旧尺寸字段', () => {
  const canvas = canvasSetup()
  const node = canvas.nodes.value[0]
  node.data.parameters = { size: '1536x1024', quality: 'high' }
  canvas.syncModelParameters(node, { parameters: { fields: [{ key: 'aspect_ratio', default: '1:1' }, { key: 'quality', default: 'medium' }] } })
  assert.deepEqual(node.data.parameters, { aspect_ratio: '3:2', quality: 'high' })
  canvas.syncModelParameters(node, { parameters: { fields: [{ key: 'size', default: 'auto' }, { key: 'image_size', default: '2K' }] } })
  assert.deepEqual(node.data.parameters, { aspect_ratio: '3:2', image_size: '2K' })
})

test('端口跟随光标，缩放后位移一致，限制最大偏移并在离开时复位', () => {
  const props = { data: makeNode('remote-imageGenerationNode', { x: 0, y: 0 }).data }
  const { moveHandle, resetHandle } = loadSetup('../src/components/CanvasNode.vue', {
    computed, ref, defineProps: () => props, inject: () => ({}), canvasActionsKey: Symbol(),
    useVueFlow: () => ({ viewport: ref({ zoom: 1 }) }), watch: () => {}, onBeforeUnmount: () => {},
  }, ['moveHandle', 'resetHandle'])
  const values = new Map()
  const element = { style: { setProperty: (key, value) => values.set(key, value), removeProperty: key => values.delete(key) } }
  for (const zoom of [0.5, 1, 2]) {
    element.getBoundingClientRect = () => ({ left: 0, top: 0, width: 18 * zoom, height: 18 * zoom })
    moveHandle({ pointerType: 'mouse', currentTarget: element, clientX: 18 * zoom, clientY: 9 * zoom })
    assert.ok(Math.abs(Number.parseFloat(values.get('--handleX')) - 2.7) < 0.000001)
    assert.equal(Number.parseFloat(values.get('--handleY')), 0)
  }
  moveHandle({ pointerType: 'mouse', currentTarget: element, clientX: 1000, clientY: 1000 })
  assert.ok(Math.hypot(Number.parseFloat(values.get('--handleX')), Number.parseFloat(values.get('--handleY'))) <= 6.000001)
  resetHandle({ currentTarget: element })
  assert.equal(values.size, 0)
  moveHandle({ pointerType: 'touch', currentTarget: element, clientX: 1000, clientY: 1000 })
  assert.equal(values.size, 0)
})
