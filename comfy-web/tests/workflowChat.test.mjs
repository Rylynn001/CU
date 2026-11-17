import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import { computed, ref } from 'vue'

// 执行实际接口和组件脚本，替换网络及挂载副作用。
function loadScript(source, bindings, names) {
  const script = ts.createSourceFile('chat.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const statements = script.statements.filter(statement => !ts.isImportDeclaration(statement))
  const code = statements.map(statement => statement.getText(script).replace(/^export\s+/, '')).join('\n')
  const { outputText } = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } })
  return new Function(...Object.keys(bindings), `${outputText}\nreturn { ${names.join(', ')} }`)(...Object.values(bindings))
}

const answer = '人生的意义可以由自己创造。'
const response = { session_id: '31', reply: answer, intent: 'chat', workflow_ready: false, tasks: [] }

function apiWithEvents(events) {
  const text = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('')
  const bytes = new TextEncoder().encode(text)
  const api = loadScript(readFileSync(new URL('../src/api/workflow.ts', import.meta.url), 'utf8'), {
    authFetch: async () => new Response(new ReadableStream({ start(controller) {
      // 跨网络分块解析，包含被拆开的中文字符。
      for (let offset = 0; offset < bytes.length; offset += 7) controller.enqueue(bytes.slice(offset, offset + 7))
      controller.close()
    } })),
  }, ['sendWorkflowMessageStream'])
  return api.sendWorkflowMessageStream
}

function panelWithStream(sendWorkflowMessageStream, overrides = {}) {
  const { descriptor } = parse(readFileSync(new URL('../src/components/AiChatPanel.vue', import.meta.url), 'utf8'))
  const noop = () => {}
  return loadScript(descriptor.scriptSetup.content, {
    ref, computed, defineProps: () => ({ canvasId: 1, prepareCanvas: async () => {} }), defineEmits: () => noop,
    watch: noop, onMounted: noop, onUnmounted: noop,
    nextTick: async callback => callback?.(),
    sendWorkflowMessageStream,
    getUserSessions: async () => [],
    getSessionHistory: async () => ({ conversations: [], tasks: [] }),
    ...overrides,
  }, ['handleSubmit', 'messages', 'currentSessionId', 'isProcessing', 'loadSessions', 'selectSession', 'sessions', 'createNewSession',
    'openGenerationDialog', 'confirmGeneration', 'generationType', 'generationModelId', 'imageCount', 'imageAspectRatio', 'imageQuality',
    'videoRatio', 'videoResolution', 'videoDuration', 'availableModels', 'activeTasks', 'pollTasksOnce'])
}

const submission = { prompt: '人生的意义是什么', model: { id: '7' }, useWebSearch: false, attachedFile: null }

test('长任务先确认两类参数再统一提交，保持计划编号和8秒时长', async () => {
  const sent = []
  const panel = panelWithStream(async request => { sent.push(request); return response })
  panel.availableModels.value = [{ id: '7' }]
  panel.openGenerationDialog({ media_type: 'plan', plan_id: 'plan-1', prompt: '生成角色、合影、视频', models_by_type: { image: [], video: [] }, steps: [
    { id: 'man', label: '男主', media_type: 'image', prompt: '男主', depends_on: [] },
    { id: 'woman', label: '女主', media_type: 'image', prompt: '女主', depends_on: [] },
    { id: 'photo', label: '合影', media_type: 'image', prompt: '合影', depends_on: ['man', 'woman'] },
    { id: 'video', label: '视频', media_type: 'video', prompt: '挥手', depends_on: ['photo'], duration: 8 },
  ] })
  assert.equal(panel.imageCount.value, 1)
  panel.generationModelId.value = 5
  panel.imageAspectRatio.value = '1:1'
  panel.imageQuality.value = 'high'
  await panel.confirmGeneration()
  assert.equal(sent.length, 0)
  assert.equal(panel.generationType.value, 'video')
  assert.equal(panel.videoDuration.value, 8)
  panel.generationModelId.value = 6
  panel.videoRatio.value = '16:9'
  panel.videoResolution.value = '720p'
  await panel.confirmGeneration()
  assert.equal(sent.length, 1)
  assert.equal(sent[0].generation_options.plan_id, 'plan-1')
  assert.equal(sent[0].generation_options.image.model, 5)
  assert.equal(sent[0].generation_options.video.duration, 8)
})

test('等待依赖的任务通过持久会话查询进度，不使用尚不存在的生成任务编号', async () => {
  let reads = 0
  const panel = panelWithStream(async () => response, {
    getSessionHistory: async () => { reads++; return { tasks: [{ execution_id: 'next', status: 'running' }] } },
  })
  panel.currentSessionId.value = '31'
  panel.activeTasks.value = [{ execution_id: 'waiting', status: 'queued' }]
  await panel.pollTasksOnce()
  assert.equal(reads, 1)
  assert.equal(panel.activeTasks.value[0].execution_id, 'next')
})

test('流式读取忽略空值和非文字片段，保留中文完整回复', async () => {
  const deltas = []
  const send = apiWithEvents([
    ['delta', { text: null }], ['delta', {}], ['delta', { text: 42 }],
    ['delta', { text: '' }], ['delta', { text: answer }], ['done', response],
  ])
  const result = await send({ message: submission.prompt, model_id: 7 }, () => {}, text => deltas.push(text))
  assert.deepEqual(deltas, [answer])
  assert.equal(result.reply, answer)
})

test('最终回复修正中间片段，界面不会停留在 null 或不完整文字', async () => {
  const panel = panelWithStream(async (_request, _progress, delta) => {
    delta(null)
    delta('未完成的片段')
    return response
  })
  await panel.handleSubmit(submission)
  assert.equal(panel.messages.value.at(-1).message, answer)
  assert.equal(panel.isProcessing.value, false)
})

test('完整流式答案在最终事件后不重复拼接', async () => {
  const panel = panelWithStream(apiWithEvents([['delta', { text: answer }], ['done', response]]))
  await panel.handleSubmit(submission)
  assert.equal(panel.messages.value.at(-1).message, answer)
  assert.equal(panel.messages.value.at(-1).failed, undefined)
})

test('流式错误显示失败信息，且不会当成正常回复', async () => {
  const panel = panelWithStream(apiWithEvents([['error', { message: '模型服务不可用' }]]))
  await panel.handleSubmit(submission)
  assert.equal(panel.messages.value.at(-1).message, '模型服务不可用')
  assert.equal(panel.messages.value.at(-1).failed, true)
  assert.equal(panel.isProcessing.value, false)
})

test('模型和工具事件按顺序保存在对应助手消息中', async () => {
  const traces = [
    { type: 'model_request', round: 1, model: 'selected-model', message_count: 1, tools: [] },
    { type: 'tool_call', round: 1, call_id: 'image-1', name: 'txt2img', input: { prompt: '猫' } },
    { type: 'tool_result', round: 1, call_id: 'image-1', name: 'txt2img', output: { task_id: 'task-1' } },
  ]
  const panel = panelWithStream(apiWithEvents([...traces.map(trace => ['trace', trace]), ['done', response]]))
  await panel.handleSubmit(submission)
  assert.deepEqual(panel.messages.value.at(-1).events, traces)
  assert.equal(panel.messages.value[0].events, undefined)
})

test('发送消息前保存画布，消息与历史请求都携带当前画布编号', async () => {
  const order = []
  const requests = []
  const panel = panelWithStream(async request => {
    order.push('发送消息')
    requests.push(request)
    return response
  }, {
    defineProps: () => ({ canvasId: 12, prepareCanvas: async () => { order.push('保存画布') } }),
    getUserSessions: async canvasId => { assert.equal(canvasId, 12); return [] },
  })
  await panel.handleSubmit(submission)
  assert.deepEqual(order, ['保存画布', '发送消息'])
  assert.equal(requests[0].canvas_id, 12)
})

test('切换历史窗口与新窗口时清空上一窗口内容', async () => {
  const panel = panelWithStream(async () => response, {
    getSessionHistory: async (sid, canvasId) => {
      assert.equal(sid, '82')
      assert.equal(canvasId, 1)
      return { conversations: [{ role: 'user', message: '窗口二' }], tasks: [] }
    },
  })
  await panel.handleSubmit(submission)
  await panel.selectSession('82')
  assert.equal(panel.currentSessionId.value, '82')
  assert.deepEqual(panel.messages.value.map(item => item.message), ['窗口二'])
  panel.createNewSession()
  assert.equal(panel.currentSessionId.value, undefined)
  assert.deepEqual(panel.messages.value, [])
})

test('收到节点变化事件后通知画布刷新，不依赖最终聊天成功', async () => {
  const changes = []
  const panel = panelWithStream(apiWithEvents([
    ['canvas_changed', { canvas_id: 1 }], ['error', { message: '后续回复失败' }],
  ]), { defineEmits: () => (event, value) => { if (event === 'canvas-changed') changes.push(value) } })
  await panel.handleSubmit(submission)
  assert.deepEqual(changes, [1, 1])
})

test('画布合并保留本地提示词和已删除节点，只补入新节点及任务结果', () => {
  const { descriptor } = parse(readFileSync(new URL('../src/views/Canvas.vue', import.meta.url), 'utf8'))
  const script = ts.createSourceFile('canvas.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
  const declaration = script.statements.find(statement => ts.isFunctionDeclaration(statement) && statement.name.text === 'mergeGenerationNodes')
  const nodes = ref([{ id: 'existing', data: { prompt: '正在编辑', outputs: {} } }])
  const savedSnapshot = ref(JSON.stringify({ document: { nodes: [{ id: 'existing' }, { id: 'deleted' }] } }))
  const { mergeGenerationNodes } = loadScript(declaration.getText(script), { nodes, savedSnapshot }, ['mergeGenerationNodes'])
  const task = { taskId: 'task-1', historyId: 7, state: 'completed' }
  mergeGenerationNodes([
    { id: 'existing', data: { prompt: '旧提示词', executionId: 'exec-1', task, outputs: { image: { value: { assetIds: [9] } } } } },
    { id: 'deleted', data: {} },
    { id: 'new-agent-node', data: { prompt: '小猫' } },
  ])
  assert.deepEqual(nodes.value.map(node => node.id), ['existing', 'new-agent-node'])
  assert.equal(nodes.value[0].data.prompt, '正在编辑')
  assert.equal(nodes.value[0].data.task.state, 'completed')
  assert.deepEqual(nodes.value[0].data.outputs.image.value.assetIds, [9])
})

function executionTrace(events, processing = false, failed = false) {
  const { descriptor } = parse(readFileSync(new URL('../src/components/AiExecutionTrace.vue', import.meta.url), 'utf8'))
  return loadScript(descriptor.scriptSetup.content, {
    ref, computed, watch: () => {}, defineProps: () => ({ events, processing, failed }),
  }, ['entries', 'toolState', 'toolError'])
}

test('工具结果按轮次和调用编号配对，等待确认和失败状态正确显示', () => {
  const call = { type: 'tool_call', round: 1, call_id: 'same-id', name: 'txt2img', input: { prompt: '猫' } }
  const events = [
    call, { ...call, round: 2 },
    { type: 'tool_result', round: 2, call_id: 'same-id', name: 'txt2img', output: { error: '模型不可用' } },
    { type: 'tool_result', round: 1, call_id: 'same-id', name: 'txt2img', output: { selection_required: { media_type: 'image' } } },
  ]
  const trace = executionTrace(events)
  assert.equal(trace.entries.value.length, 2)
  assert.equal(trace.toolState(trace.entries.value[0]), 'approval-requested')
  assert.equal(trace.toolState(trace.entries.value[1]), 'output-error')
  assert.equal(trace.toolError(trace.entries.value[1]), '模型不可用')
})

test('执行中、中断和成功完成的工具不会混淆', () => {
  const call = { type: 'tool_call', round: 1, call_id: 'id', name: 'txt2img', input: {} }
  for (const [processing, expected] of [[true, 'input-available'], [false, 'output-error']]) {
    const trace = executionTrace([call], processing, !processing)
    assert.equal(trace.toolState(trace.entries.value[0]), expected)
  }
  const complete = executionTrace([call, { ...call, type: 'tool_result', output: { task_id: 'task-1' } }])
  assert.equal(complete.toolState(complete.entries.value[0]), 'output-available')
})
