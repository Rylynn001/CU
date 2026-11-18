import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import { parse } from '@vue/compiler-sfc'
import { computed, nextTick, reactive, ref, watch } from 'vue'

function execute(source, bindings) {
  const script = ts.createSourceFile('test.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const code = script.statements.filter(statement => !ts.isImportDeclaration(statement)).map(statement => statement.getText(script)).join('\n')
  const { outputText } = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } })
  const exports = {}
  new Function('exports', ...Object.keys(bindings), outputText)(exports, ...Object.values(bindings))
  return exports
}

function node(id, state = 'pending', historyId = 10) {
  return { id, type: 'remote-imageGenerationNode', data: { label: id, executionId: `execution-${id}`,
    outputs: {}, task: { taskId: `task-${id}`, historyId, state, error: state === 'failed' ? '供应商失败' : undefined } } }
}
function board(id, nodes) { return { id, name: `画布${id}`, document: { nodes, edges: [], viewport: { x: 0, y: 0, zoom: 1 }, version: 1 } } }

function setup() {
  const callbacks = new Set(), calls = [], messages = [], boards = new Map()
  const getBoard = async id => {
    calls.push(id)
    return structuredClone(boards.get(id))
  }
  let fetchTask = async () => ({ ok: true, json: async () => ({ status: 'processing' }) })
  let getCanvas = getBoard
  let starts = 0
  const bindings = {
    ElMessage: { success: message => messages.push(['success', message]), error: message => messages.push(['error', message]) },
    getCanvas: id => getCanvas(id), authFetch: url => fetchTask(url),
    setInterval: callback => { starts++; callbacks.add(callback); return callback },
    clearInterval: callback => callbacks.delete(callback),
  }
  const monitor = execute(readFileSync(new URL('../src/services/canvasTaskMonitor.ts', import.meta.url), 'utf8'), bindings)
  async function flush() { await new Promise(resolve => setImmediate(resolve)) }
  return { ...monitor, callbacks, calls, messages, boards, flush,
    tick: async () => { for (const callback of callbacks) callback(); await flush() },
    setFetch: callback => { fetchTask = callback }, setGet: callback => { getCanvas = callback },
    get starts() { return starts },
  }
}

test('应用从画布切到图片和视频页后，继续查询并且只通知一次完成结果', async () => {
  const monitor = setup()
  const route = reactive({ path: '' })
  const unmounts = []
  const { descriptor } = parse(readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8'))
  execute(descriptor.scriptSetup.content, { computed, ref, watch, useRoute: () => route,
    localStorage: { getItem: key => key === 'token' ? 'test-token' : null },
    onBeforeUnmount: callback => unmounts.push(callback), ...monitor,
  })
  route.path = '/canvas'
  await nextTick()
  const pending = node('图片生成')
  monitor.boards.set(1, board(1, [pending]))
  monitor.trackCanvasTasks(1, '画布1', [pending])
  monitor.setActiveCanvas(1)
  let updates = 0
  const unsubscribe = monitor.subscribeCanvasTasks(() => { updates++ })
  await monitor.tick()
  assert.equal(updates, 1)
  // 模拟 Canvas.vue 卸载；根组件和任务跟踪继续存在。
  unsubscribe()
  monitor.setActiveCanvas()
  for (const path of ['/image', '/video']) {
    route.path = path
    await nextTick()
    const previous = monitor.calls.length
    await monitor.tick()
    assert.ok(monitor.calls.length > previous, `${path} 页面仍应查询原画布`)
  }
  monitor.boards.set(1, board(1, [node('图片生成', 'completed')]))
  await monitor.tick()
  assert.deepEqual(monitor.messages, [['success', '画布1 · 图片生成已完成']])
  assert.equal(updates, 1, '已卸载的画布不再收到更新')
  await monitor.tick()
  assert.equal(monitor.messages.length, 1)
  assert.equal(monitor.starts, 1, '切换页面不创建重复定时器')
  route.path = '/login'
  await nextTick()
  assert.equal(monitor.callbacks.size, 0)
  unmounts.forEach(callback => callback())
})

test('切换画布后，两个画布独立跟踪，失败提示保留原画布名称', async () => {
  const monitor = setup()
  monitor.startCanvasTaskMonitor()
  for (const id of [1, 2]) {
    const pending = node(`节点${id}`)
    monitor.boards.set(id, board(id, [pending]))
    monitor.trackCanvasTasks(id, `画布${id}`, [pending])
  }
  monitor.setActiveCanvas(2)
  monitor.boards.set(1, board(1, [node('节点1', 'failed')]))
  await monitor.tick()
  assert.deepEqual(new Set(monitor.calls), new Set([1, 2]))
  assert.deepEqual(monitor.messages, [['error', '画布1 · 节点1失败：供应商失败']])
  monitor.stopCanvasTaskMonitor()
})

test('短暂查询失败或 Redis 任务过期继续跟踪，不重复提交生成', async () => {
  const monitor = setup()
  const pending = node('图片')
  monitor.trackCanvasTasks(1, '画布1', [pending])
  monitor.boards.set(1, board(1, [pending]))
  monitor.startCanvasTaskMonitor()
  let attempts = 0
  monitor.setGet(async id => {
    monitor.calls.push(id)
    if (++attempts === 1) throw new Error('网络中断')
    return structuredClone(monitor.boards.get(id))
  })
  monitor.setFetch(async url => {
    assert.equal(url, '/api/api-proxy/task/task-图片')
    return { ok: false, status: 404 }
  })
  await monitor.tick()
  await monitor.tick()
  assert.equal(monitor.messages.length, 0)
  monitor.boards.set(1, board(1, [node('图片', 'completed')]))
  await monitor.tick()
  assert.equal(monitor.messages.length, 1)
  monitor.stopCanvasTaskMonitor()
})

test('尚未提交的依赖步骤也持续跟踪，但不会拿执行编号查询 Redis', async () => {
  const monitor = setup()
  const pending = node('等待前置步骤', 'pending', 0)
  monitor.trackCanvasTasks(1, '画布1', [pending])
  monitor.boards.set(1, board(1, [pending]))
  monitor.setFetch(async () => assert.fail('排队步骤没有真实任务编号'))
  monitor.startCanvasTaskMonitor()
  await monitor.tick()
  assert.equal(monitor.calls.length, 1)
  monitor.boards.set(1, board(1, [node('等待前置步骤', 'completed')]))
  await monitor.tick()
  assert.equal(monitor.messages.length, 1)
  monitor.stopCanvasTaskMonitor()
})

test('慢任务不阻塞其他画布，重复刷新合并为同一个请求', async () => {
  const monitor = setup()
  let release
  const slow = new Promise(resolve => { release = resolve })
  monitor.setGet(async id => id === 1 ? slow : board(2, [node('快任务', 'completed')]))
  monitor.trackCanvasTasks(1, '画布1', [node('慢任务')])
  monitor.trackCanvasTasks(2, '画布2', [node('快任务')])
  monitor.startCanvasTaskMonitor()
  await monitor.tick()
  assert.equal(monitor.messages.length, 1)
  assert.equal(monitor.refreshCanvasTasks(1), monitor.refreshCanvasTasks(1))
  release(board(1, [node('慢任务', 'completed')]))
  await monitor.flush()
  assert.equal(monitor.messages.length, 2)
  monitor.stopCanvasTaskMonitor()
})

test('退出登录后丢弃旧请求结果，不能向下个账号发出通知', async () => {
  const monitor = setup()
  let release
  monitor.setGet(() => new Promise(resolve => { release = resolve }))
  monitor.trackCanvasTasks(1, '旧账号画布', [node('图片')])
  const request = monitor.refreshCanvasTasks(1)
  monitor.stopCanvasTaskMonitor()
  monitor.startCanvasTaskMonitor()
  release(board(1, [node('图片', 'completed')]))
  await request
  assert.equal(monitor.messages.length, 0)
  monitor.stopCanvasTaskMonitor()
})

test('视频查询完成后立即重新读取画布结果，订阅者拿到最终输出', async () => {
  const monitor = setup()
  monitor.trackCanvasTasks(1, '画布1', [node('视频')])
  monitor.boards.set(1, board(1, [node('视频')]))
  monitor.setFetch(async () => {
    monitor.boards.set(1, board(1, [node('视频', 'completed')]))
    return { ok: true, json: async () => ({ status: 'completed' }) }
  })
  let received
  monitor.subscribeCanvasTasks(value => { received = value })
  await monitor.refreshCanvasTasks(1)
  assert.equal(received.document.nodes[0].data.task.state, 'completed')
  assert.equal(monitor.calls.length, 2)
  assert.equal(monitor.messages.length, 1)
})
