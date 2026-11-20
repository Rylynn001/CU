import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import { computed, reactive, ref, watch, nextTick, effectScope } from 'vue'

// 执行实际接口和组件脚本，替换网络及挂载副作用。
function loadScript(source, bindings, names) {
  const script = ts.createSourceFile('chat.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const statements = script.statements.filter(statement => !ts.isImportDeclaration(statement))
  const code = statements.map(statement => statement.getText(script).replace(/^export\s+/, '')).join('\n')
  const { outputText } = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } })
  return new Function(...Object.keys(bindings), `${outputText}\nreturn { ${names.join(', ')} }`)(...Object.values(bindings))
}

const aspectRatios = loadScript(readFileSync(new URL('../src/constants/aspectRatios.ts', import.meta.url), 'utf8'), {}, ['IMAGE_ASPECT_RATIOS', 'VIDEO_ASPECT_RATIOS'])

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
    ...aspectRatios, ref, computed, defineProps: () => ({ canvasId: 1, prepareCanvas: async () => {} }), defineEmits: () => noop,
    watch: noop, onMounted: noop, onUnmounted: noop, defineExpose: noop,
    nextTick: async callback => callback?.(),
    sendWorkflowMessageStream,
    getUserSessions: async () => [],
    getSessionHistory: async () => ({ conversations: [], tasks: [] }),
    ElMessage: { info: noop, warning: noop, error: noop },
    ...overrides,
  }, ['handleSubmit', 'stopProcessing', 'canStop', 'messages', 'currentSessionId', 'isProcessing', 'loadSessions', 'selectSession', 'sessions', 'createNewSession',
    'openGenerationDialog', 'confirmGeneration', 'generationType', 'generationModelId', 'imageCount', 'imageAspectRatio', 'imageQuality',
    'videoRatio', 'videoResolution', 'videoDuration', 'videoDurationMin', 'videoDurationMax', 'videoDurationStep', 'availableModels', 'activeTasks', 'pollTasksOnce',
    'canvasDialog', 'canvasName', 'canvasDialogError', 'confirmCanvasDialog', 'openCanvasDialog', 'selectAssets', 'selectedAssets', 'referenceItems', 'uploadAsset',
    'pendingGenerationPrompt', 'pendingPlan', 'generationDialogError', 'generationDialogOpen', 'loadSkills', 'skills', 'selectedSkillId', 'skillsError', 'skillsLoading', 'startPromptOptimization', 'optimizationTarget'])
}

const submission = { prompt: '人生的意义是什么', model: { id: '7' }, useWebSearch: false, attachedFile: null }

test('停止会中断流请求、保留已有回复，并可立即发送下一轮', async () => {
  let started
  const ready = new Promise(resolve => { started = resolve })
  let aborted = false
  const api = loadScript(readFileSync(new URL('../src/api/workflow.ts', import.meta.url), 'utf8'), {
    authFetch: async (_, options) => new Response(new ReadableStream({ start(controller) {
      options.signal.addEventListener('abort', () => {
        aborted = true
        controller.error(options.signal.reason)
      }, { once: true })
      controller.enqueue(new TextEncoder().encode('event: delta\ndata: {"text":"已经收到的回复"}\n\n'))
    } })),
  }, ['sendWorkflowMessageStream'])
  let calls = 0
  const panel = panelWithStream(async (...args) => {
    if (++calls > 1) return response
    const onDelta = args[2]
    args[2] = text => { onDelta(text); started() }
    return api.sendWorkflowMessageStream(...args)
  })
  const pending = panel.handleSubmit(submission)
  await ready
  assert.equal(panel.canStop.value, true)
  panel.stopProcessing()
  await pending
  assert.equal(aborted, true)
  assert.equal(panel.isProcessing.value, false)
  assert.equal(panel.canStop.value, false)
  assert.equal(panel.messages.value.at(-1).message, '已经收到的回复')
  assert.equal(panel.messages.value.at(-1).stopped, true)
  assert.notEqual(panel.messages.value.at(-1).failed, true)
  await panel.handleSubmit(submission)
  assert.equal(panel.messages.value.at(-1).message, answer)
  assert.equal(panel.messages.value.at(-1).stopped, undefined)
})

test('准备画布时停止，不再发送模型请求', async () => {
  let finishCanvas
  const canvas = new Promise(resolve => { finishCanvas = resolve })
  let requests = 0
  const panel = panelWithStream(async () => { requests++; return response }, {
    defineProps: () => ({ canvasId: 1, prepareCanvas: () => canvas }),
  })
  const pending = panel.handleSubmit(submission)
  panel.stopProcessing()
  finishCanvas(1)
  await pending
  assert.equal(requests, 0)
  assert.equal(panel.messages.value.at(-1).stopped, true)
  assert.equal(panel.isProcessing.value, false)
})

test('技能前缀直接写入输入框，切换和取消保留正文，空模板不能发送', async () => {
  const scope = effectScope()
  try {
    const props = reactive({ models: [{ id: '7', name: '对话模型' }], skillId: '', references: [] })
    const textInput = ref('夏日茶饮，瓶身有水珠')
    const { descriptor } = parse(readFileSync(new URL('../src/components/AiChatComposer.vue', import.meta.url), 'utf8'))
    const composer = scope.run(() => loadScript(descriptor.scriptSetup.content, {
      computed, ref, watch, nextTick, defineProps: () => props, withDefaults: value => value,
      defineEmits: () => () => {}, defineExpose: () => {},
      usePromptInputProvider: () => ({ textInput, setTextInput: text => { textInput.value = text } }),
    }, ['disabled', 'usage', 'maxTokens']))
    props.skillId = 'gpt-image-2-style-library'
    assert.match(textInput.value, /^使用 gpt-image-2-style-library 技能优化以下提示词，只要文字，不生成图片：/)
    assert.ok(textInput.value.endsWith('夏日茶饮，瓶身有水珠'))
    props.skillId = 'seedance-prompt'
    assert.match(textInput.value, /^使用 Seedance 技能优化以下提示词，只要文字，不生成视频或图片：/)
    assert.ok(!textInput.value.includes('gpt-image-2-style-library'))
    props.skillId = ''
    assert.equal(textInput.value, '夏日茶饮，瓶身有水珠')
    textInput.value = ''
    props.skillId = 'seedance-prompt'
    assert.equal(composer.disabled.value, true)
    textInput.value += '猫在跑'
    assert.equal(composer.disabled.value, false)
    props.requiresSkill = true
    props.skillId = ''
    assert.equal(composer.disabled.value, true)
    props.skillId = 'image-prompt-reverse'
    assert.equal(composer.disabled.value, false)
    assert.match(textInput.value, /根据引用的图片反推提示词/)
  } finally { scope.stop() }
})

test('视频时长随模型范围和步长校正，并将滑杆值发送给生成接口', async () => {
  const scope = effectScope()
  try {
    const sent = []
    const panel = scope.run(() => panelWithStream(async request => { sent.push(request); return response }, { watch }))
    panel.availableModels.value = [{ id: '7' }]
    panel.openGenerationDialog({ media_type: 'video', prompt: '人物挥手', models: [
      { id: 1, name: 'api-a', description: '视频模型甲', parameters: { fields: [{ key: 'duration', min: 4, max: 30, step: 1, default: 8 }] } },
      { id: 2, name: 'api-b', description: '视频模型乙', parameters: { fields: [{ key: 'duration', min: 6, max: 12, step: 2, default: 8 }] } },
    ] })
    panel.generationModelId.value = 1
    await nextTick()
    assert.equal(panel.videoDuration.value, 8)
    panel.videoDuration.value = 29
    panel.generationModelId.value = 2
    await nextTick()
    assert.equal(panel.videoDuration.value, 12)
    assert.deepEqual([panel.videoDurationMin.value, panel.videoDurationMax.value, panel.videoDurationStep.value], [6, 12, 2])
    panel.videoDuration.value = 4
    panel.generationModelId.value = 1
    await nextTick()
    panel.generationModelId.value = 2
    await nextTick()
    assert.equal(panel.videoDuration.value, 6)
    panel.videoDuration.value = 10
    panel.videoRatio.value = '16:9'
    panel.videoResolution.value = '720p'
    await panel.confirmGeneration()
    assert.equal(sent[0].generation_options.duration, 10)
    assert.equal(sent[0].generation_options.model, 2)
  } finally { scope.stop() }
})

test('计划中指定的时长超出模型范围时阻止提交，不擅自修改计划', async () => {
  const scope = effectScope()
  try {
    const sent = []
    const panel = scope.run(() => panelWithStream(async request => { sent.push(request); return response }, { watch }))
    panel.availableModels.value = [{ id: '7' }]
    panel.openGenerationDialog({ media_type: 'plan', plan_id: 'duration-test', prompt: '视频计划', steps: [
      { id: 'v1', label: '长视频', media_type: 'video', prompt: '人物挥手', depends_on: [], duration: 20 },
    ], models_by_type: { video: [{ id: 2, name: 'api-b', parameters: { fields: [{ key: 'duration', min: 4, max: 12, step: 1 }] } }] } })
    panel.generationModelId.value = 2
    panel.videoRatio.value = '16:9'
    panel.videoResolution.value = '720p'
    await nextTick()
    await panel.confirmGeneration()
    assert.equal(sent.length, 0)
    assert.equal(panel.videoDuration.value, 20)
    assert.equal(panel.pendingPlan.value.steps[0].duration, 20)
    assert.match(panel.generationDialogError.value, /4–12/)
  } finally { scope.stop() }
})

test('聊天确认的全部比例通过唯一 aspect_ratio 字段提交', async () => {
  for (const [media, ratios] of [['image', aspectRatios.IMAGE_ASPECT_RATIOS], ['video', aspectRatios.VIDEO_ASPECT_RATIOS]]) {
    const sent = []
    const panel = panelWithStream(async request => { sent.push(request); return response })
    panel.availableModels.value = [{ id: '7' }]
    for (const option of ratios) {
      panel.openGenerationDialog({ media_type: media, prompt: '测试比例', models: [{ id: 4 }] })
      panel.generationModelId.value = 4
      if (media === 'image') {
        panel.imageCount.value = 1
        panel.imageAspectRatio.value = option.value
        panel.imageQuality.value = 'high'
      } else {
        panel.videoRatio.value = option.value
        panel.videoResolution.value = '720p'
        panel.videoDuration.value = 8
      }
      await panel.confirmGeneration()
      const options = sent.at(-1).generation_options
      assert.equal(options.aspect_ratio, option.value)
      assert.ok(!('ratio' in options) && !('size' in options))
    }
    assert.equal(sent.length, ratios.length)
  }
})

test('技能列表刷新支持新增和移除，发送及取消选择正确传递', async () => {
  let list = [{ id: 'seedance-prompt', name: 'seedance', description: '视频提示词' }]
  const requests = []
  const panel = panelWithStream(async request => { requests.push(request); return response }, { getChatSkills: async () => list })
  await panel.loadSkills()
  assert.equal(panel.skills.value[0].id, 'seedance-prompt')
  panel.selectedSkillId.value = 'seedance-prompt'
  await panel.handleSubmit({ ...submission, skillId: panel.selectedSkillId.value })
  assert.equal(requests[0].skill_id, 'seedance-prompt')
  assert.equal(panel.selectedSkillId.value, '')
  list = [{ id: 'new-skill', name: '新技能', description: '' }]
  await panel.loadSkills()
  assert.equal(panel.selectedSkillId.value, '')
  await panel.handleSubmit({ ...submission, skillId: undefined })
  assert.equal(requests[1].skill_id, undefined)
  assert.equal(panel.skills.value[0].id, 'new-skill')
})

test('技能仅在成功发送后清空，失败保留选择供重试', async () => {
  let failed = true
  const panel = panelWithStream(async () => { if (failed) throw new Error('网络失败'); return response })
  panel.selectedSkillId.value = 'custom'
  await panel.handleSubmit({ ...submission, skillId: 'custom' })
  assert.equal(panel.selectedSkillId.value, 'custom')
  failed = false
  await panel.handleSubmit({ ...submission, skillId: 'custom' })
  assert.equal(panel.selectedSkillId.value, '')
})

test('节点优化携带参数和局部素材，多轮追问后仅最终结果可回填，新会话退出优化', async () => {
  const requests = []
  const panel = panelWithStream(async request => {
    requests.push(request)
    return requests.length === 1 ? { ...response, reply: '请确认时长' }
      : { ...response, reply: '已优化', optimized_prompt: '@图片1 人物缓慢转身，持续8秒' }
  })
  panel.availableModels.value = [{ id: '7' }]
  const target = { canvasId: 1, nodeId: 'n1', label: '视频生成', prompt: '@图片1 人物转身', mediaType: 'video', parameters: { ratio: '16:9' },
    references: [{ id: 19, type: 'image', label: '人物', mention: '@图片1', url: '/person.png' }] }
  assert.equal(await panel.startPromptOptimization(target, 'seedance-prompt'), true)
  assert.equal(requests[0].prompt_optimization, true)
  assert.equal(requests[0].skill_id, 'seedance-prompt')
  assert.match(requests[0].message, /16:9/)
  assert.deepEqual(requests[0].asset_ids, [19])
  assert.equal(panel.messages.value.at(-1).optimizedPrompt, undefined)
  assert.equal(panel.selectedSkillId.value, 'seedance-prompt')
  assert.equal(requests[0].optimization_node_id, 'n1')
  assert.equal(await panel.handleSubmit({ ...submission, prompt: '8秒' }), false)
  assert.equal(requests.length, 1)
  await panel.handleSubmit({ ...submission, prompt: '8秒', skillId: panel.selectedSkillId.value })
  assert.equal(requests[1].prompt_optimization, true)
  assert.equal(requests[1].skill_id, 'seedance-prompt')
  assert.equal(panel.messages.value.at(-1).optimizedPrompt, '@图片1 人物缓慢转身，持续8秒')
  panel.createNewSession()
  assert.equal(panel.optimizationTarget.value, undefined)
  await panel.handleSubmit(submission)
  assert.equal(requests[2].prompt_optimization, false)
})

test('节点反推发送目标编号，未选技能不能启动，对话反推正确提交所引用图片', async () => {
  const requests = []
  const panel = panelWithStream(async request => { requests.push(request); return response }, {
    defineProps: () => ({ canvasId: 1, prepareCanvas: async () => {}, references: [
      { id: 19, type: 'image', label: '人物', mention: '@图片1', url: '/person.png' },
      { id: 28, type: 'image', label: '风景', mention: '@图片2', url: '/landscape.png' },
    ] }),
  })
  panel.availableModels.value = [{ id: '7' }]
  const target = { canvasId: 1, nodeId: 'target', prompt: '', mediaType: 'image', parameters: {}, references: [] }
  assert.equal(await panel.startPromptOptimization(target, ''), false)
  assert.equal(panel.optimizationTarget.value, undefined)
  assert.equal(requests.length, 0)
  assert.equal(await panel.startPromptOptimization(target, 'image-prompt-reverse'), true)
  assert.equal(requests[0].optimization_node_id, 'target')
  assert.equal(requests[0].skill_id, 'image-prompt-reverse')
  assert.match(requests[0].message, /上游参考图片反推提示词/)
  panel.createNewSession()
  await panel.handleSubmit({ ...submission, prompt: '请反推 @图片2 的提示词', skillId: 'image-prompt-reverse' })
  assert.deepEqual(requests[1].asset_ids, [28])
  assert.deepEqual(requests[1].asset_mentions, { 28: '@图片2' })
  assert.equal(requests[1].prompt_optimization, false)
  assert.equal(requests[1].optimization_node_id, undefined)
})

test('技能加载失败可重试，不留下扫描中的状态', async () => {
  let failed = true
  const panel = panelWithStream(async () => response, { getChatSkills: async () => {
    if (failed) throw new Error('技能列表加载失败')
    return []
  } })
  await panel.loadSkills()
  assert.equal(panel.skillsError.value, '技能列表加载失败')
  assert.equal(panel.skillsLoading.value, false)
  failed = false
  await panel.loadSkills()
  assert.equal(panel.skillsError.value, '')
})

test('图片与视频确认发送编辑后的提示词，隐藏内部映射且阻止空白提示词', async () => {
  for (const media_type of ['image', 'video']) {
    const sent = []
    const panel = panelWithStream(async request => { sent.push(request); return response })
    panel.availableModels.value = [{ id: '7' }]
    panel.openGenerationDialog({ media_type, prompt: '原描述\n\n本次上传的参考素材对应关系：\n保留映射', models: [] })
    assert.equal(panel.pendingGenerationPrompt.value, '原描述')
    panel.generationModelId.value = 5
    panel.imageCount.value = 1
    panel.imageAspectRatio.value = '1:1'
    panel.imageQuality.value = 'high'
    panel.videoRatio.value = '16:9'
    panel.videoResolution.value = '720p'
    panel.videoDuration.value = 8
    panel.pendingGenerationPrompt.value = '  '
    await panel.confirmGeneration()
    assert.equal(sent.length, 0)
    assert.match(panel.generationDialogError.value, /提示词/)
    assert.equal(panel.generationDialogOpen.value, true)
    panel.pendingGenerationPrompt.value = '  用户修改后的描述  '
    await panel.confirmGeneration()
    assert.equal(sent[0].generation_options.prompt, '用户修改后的描述')
    assert.equal(sent[0].generation_options.media_type, media_type)
    assert.equal(sent[0].skill_id, undefined)
  }
})

test('多步提示词编辑保留到两类参数确认结束，且不修改原计划对象', async () => {
  const sent = []
  const panel = panelWithStream(async request => { sent.push(request); return response })
  panel.availableModels.value = [{ id: '7' }]
  const plan = { media_type: 'plan', plan_id: 'p1', prompt: '图片转视频', models_by_type: { image: [], video: [] }, steps: [
    { id: 's1', label: '图片', media_type: 'image', prompt: '原图', depends_on: [] },
    { id: 's2', label: '视频', media_type: 'video', prompt: '原视频', depends_on: ['s1'], duration: 8 },
  ] }
  panel.openGenerationDialog(plan)
  panel.pendingPlan.value.steps[0].prompt = '新图片描述'
  panel.pendingPlan.value.steps[1].prompt = '新视频描述'
  panel.generationModelId.value = 5
  panel.imageAspectRatio.value = '1:1'
  panel.imageQuality.value = 'high'
  await panel.confirmGeneration()
  assert.equal(sent.length, 0)
  assert.equal(panel.pendingPlan.value.steps[0].prompt, '新图片描述')
  panel.generationModelId.value = 6
  panel.videoRatio.value = '16:9'
  panel.videoResolution.value = '720p'
  await panel.confirmGeneration()
  assert.deepEqual(sent[0].generation_options.step_prompts, { s1: '新图片描述', s2: '新视频描述' })
  assert.equal(sent[0].generation_options.plan_id, 'p1')
  assert.equal(plan.steps[0].prompt, '原图')
  assert.deepEqual(panel.pendingPlan.value.steps[1].depends_on, ['s1'])
})

test('引用按界面编号发送，提示词倒序或重复提及不会倒置附件', async () => {
  const requests = []
  const references = [727, 728, 729].map((id, index) => ({ id, url: `/${id}.png`, type: 'image', referenceId: index + 1, mention: `@图片${index + 1}`, label: '素材' }))
  const panel = panelWithStream(async request => { requests.push(request); return response }, {
    defineProps: () => ({ canvasId: 1, prepareCanvas: async () => {}, references }),
  })
  await panel.handleSubmit({ ...submission, prompt: '@图片3在左边，@图片2在右边，@图片1在中间，再参考@图片3' })
  assert.deepEqual(requests[0].asset_ids, [727, 728, 729])
  assert.deepEqual(requests[0].asset_mentions, { 727: '@图片1', 728: '@图片2', 729: '@图片3' })
  assert.deepEqual(panel.messages.value[0].assets.map(asset => asset.id), [727, 728, 729])
  await panel.handleSubmit({ ...submission, prompt: '只参考@图片3' })
  assert.deepEqual(requests[1].asset_ids, [729])
  assert.deepEqual(requests[1].asset_mentions, { 729: '@图片3' })
})

test('附件按选择顺序保留，重复素材不阻断后续图片，图片与视频分别编号', async () => {
  const requests = []
  const panel = panelWithStream(async request => { requests.push(request); return response })
  panel.selectAssets([{ id: 29, location: '1.png' }])
  panel.selectAssets([{ id: 29, location: '1.png' }, { id: 41, location: 'clip.mp4', asset_type: 'video' }, { id: 17, location: '2.png' }, { id: 8, location: '3.png' }])
  assert.deepEqual(panel.selectedAssets.value.map(asset => asset.id), [29, 41, 17, 8])
  await panel.handleSubmit({ ...submission, prompt: '@图片3 @视频1 @图片2 @图片1' })
  assert.deepEqual(requests[0].asset_ids, [29, 41, 17, 8])
  assert.deepEqual(requests[0].asset_mentions, { 29: '@图片1', 41: '@视频1', 17: '@图片2', 8: '@图片3' })
})

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

test('提示词追问会清理旧参数面板，不把暂停草稿作为可确认计划', async () => {
  const panel = panelWithStream(async () => ({ ...response, intent: 'generation_plan', reply: '已保留任务，请补充角色外观。', generation_request: null }))
  panel.openGenerationDialog({ media_type: 'plan', plan_id: 'old-plan', prompt: '旧计划', models_by_type: {}, steps: [
    { id: 's1', label: '角色', media_type: 'image', prompt: '旧角色描述', depends_on: [] },
    { id: 's2', label: '视频', media_type: 'video', prompt: '旧视频描述', depends_on: ['s1'] },
  ] })
  await panel.handleSubmit(submission)
  assert.equal(panel.pendingPlan.value, null)
  assert.equal(panel.generationDialogOpen.value, false)
  assert.equal(panel.generationType.value, 'none')
  assert.match(panel.messages.value.at(-1).message, /请补充角色外观/)
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

test('入口首次提交先命名，确认后使用自定义名称创建并发送任务', async () => {
  const order = []
  const panel = panelWithStream(async request => {
    order.push(['发送', request.canvas_id])
    return response
  }, {
    defineProps: () => ({ homeMode: true, prepareCanvas: async name => { order.push(['创建画布', name]); return 23 } }),
    getUserSessions: async id => { assert.equal(id, 23); return [] },
  })
  await panel.handleSubmit(submission)
  assert.deepEqual(order, [])
  assert.equal(panel.canvasDialog.value.type, 'create')
  panel.canvasName.value = '  海报方案  '
  await panel.confirmCanvasDialog()
  assert.deepEqual(order, [['创建画布', '海报方案'], ['发送', 23]])
  assert.equal(panel.messages.value.at(-1).message, answer)
})

test('优化已连接参考图的节点时自动携带图片，即使提示词没有手写图片引用', async () => {
  const requests = []
  const reference = {
    id: 91, url: '/api/api-proxy/output/reference.png', type: 'image', label: '参考图',
    referenceId: 1, mention: '@图片1',
  }
  const panel = panelWithStream(async request => { requests.push(request); return response }, {
    defineProps: () => ({ canvasId: 12, prepareCanvas: async () => {} }),
  })
  panel.optimizationTarget.value = {
    canvasId: 12, nodeId: 'image-node', label: '图片节点', prompt: '一只猫',
    mediaType: 'image', parameters: {}, references: [reference],
  }
  await panel.handleSubmit({ ...submission, prompt: '使用 gpt-image-2-style-library 优化：一只猫', skillId: 'gpt-image-2-style-library' })
  assert.deepEqual(requests[0].asset_ids, [91])
  assert.equal(requests[0].asset_mentions[91], '@图片1')
  assert.deepEqual(panel.messages.value[0].assets.map(asset => asset.id), [91])
})

test('上传成功后作为图片附件发送，上传中阻止重复提交', async () => {
  let finishUpload
  const file = { type: 'image/png', name: '参考图.png' }
  const busy = []
  const requests = []
  const panel = panelWithStream(async request => { requests.push(request); return response }, {
    uploadInputImage: input => { assert.equal(input, file); return new Promise(resolve => { finishUpload = resolve }) },
    defineEmits: () => (name, value) => { if (name === 'busy-change') busy.push(value) },
  })
  const input = { files: [file], value: '参考图.png' }
  const pending = panel.uploadAsset({ target: input })
  assert.equal(input.value, '')
  assert.equal(panel.isProcessing.value, true)
  await panel.handleSubmit(submission)
  assert.equal(requests.length, 0)
  finishUpload({ id: 91, location: 'D:\\input\\reference.png' })
  await pending
  assert.equal(panel.isProcessing.value, false)
  assert.deepEqual(busy, [true, false])
  assert.deepEqual(panel.selectedAssets.value, [{ id: 91, asset_type: 'picture', url: '/api/api-proxy/output/reference.png' }])
  await panel.handleSubmit(submission)
  assert.deepEqual(requests[0].asset_ids, [91])
  assert.equal(requests[0].asset_mentions[91], '@图片1')
})

test('上传失败保留原附件并恢复输入，非图片和超限文件不发上传请求', async () => {
  let calls = 0
  const panel = panelWithStream(async () => response, {
    uploadInputImage: async () => { calls++; throw new Error('上传失败') },
  })
  panel.selectAssets([{ id: 1, location: 'one.png' }])
  await panel.uploadAsset({ target: { files: [{ type: 'image/png' }], value: 'x' } })
  assert.equal(calls, 1)
  assert.equal(panel.isProcessing.value, false)
  assert.deepEqual(panel.selectedAssets.value.map(asset => asset.id), [1])
  await panel.uploadAsset({ target: { files: [{ type: 'video/mp4' }], value: 'x' } })
  panel.selectAssets(Array.from({ length: 9 }, (_,i) => ({ id: i + 2, location: 'x.png' })))
  await panel.uploadAsset({ target: { files: [{ type: 'image/png' }], value: 'x' } })
  assert.equal(calls, 1)
})

test('画布创建失败时不发送任务，保留失败提示供重试', async () => {
  let sent = false
  const panel = panelWithStream(async () => { sent = true; return response }, {
    defineProps: () => ({ homeMode: true, prepareCanvas: async () => { throw new Error('画布创建失败') } }),
  })
  await panel.handleSubmit(submission, undefined, '自定义画布')
  assert.equal(sent, false)
  assert.equal(panel.messages.value.at(-1).message, '画布创建失败')
  assert.equal(panel.isProcessing.value, false)
})

function canvasEntry(bindings = {}) {
  const { descriptor } = parse(readFileSync(new URL('../src/views/Canvas.vue', import.meta.url), 'utf8'))
  const script = ts.createSourceFile('canvas.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
  const prepare = script.statements.find(statement => ts.isFunctionDeclaration(statement) && statement.name.text === 'prepareChatCanvas')
  const state = { homeMode: ref(true), homeCanvasId: ref(), activeId: ref(), chatPanelOpen: ref(false), boards: ref([]) }
  const calls = []
  const api = loadScript(prepare.getText(script), {
    ...state,
    createCanvas: async () => { calls.push('创建'); return { id: 23, name: '新画布' } },
    openBoard: async id => { calls.push(['打开', id]); state.activeId.value = id; return true },
    persist: async () => { calls.push('保存') },
    ...bindings,
  }, ['prepareChatCanvas'])
  return { ...api, ...state, calls }
}

test('优化结果只回填原节点，拒绝覆盖编辑、生成中的节点及其他画布', () => {
  const { descriptor } = parse(readFileSync(new URL('../src/views/Canvas.vue', import.meta.url), 'utf8'))
  const script = ts.createSourceFile('canvas.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
  const declaration = script.statements.find(statement => ts.isFunctionDeclaration(statement) && statement.name.text === 'applyOptimizedPrompt')
  const node = { id: 'n1', data: { prompt: '原提示词' } }
  const nodes = ref([node])
  const activeId = ref(1)
  const submitting = new Set()
  const warnings = []
  const { applyOptimizedPrompt } = loadScript(declaration.getText(script), { nodes, activeId, submitting,
    ElMessage: { warning: text => warnings.push(text), success: () => {} } }, ['applyOptimizedPrompt'])
  const target = { canvasId: 1, nodeId: 'n1', prompt: '原提示词' }
  applyOptimizedPrompt(target, '优化结果')
  assert.equal(node.data.prompt, '优化结果')
  assert.equal(target.prompt, '优化结果')
  node.data.prompt = '用户编辑'
  applyOptimizedPrompt(target, '不能覆盖')
  assert.equal(node.data.prompt, '用户编辑')
  node.data.prompt = target.prompt
  submitting.add('n1')
  applyOptimizedPrompt(target, '不能覆盖')
  submitting.clear()
  activeId.value = 2
  applyOptimizedPrompt(target, '不能覆盖')
  activeId.value = 1
  nodes.value = []
  applyOptimizedPrompt(target, '不能覆盖')
  assert.equal(node.data.prompt, '优化结果')
  assert.equal(warnings.length, 4)
})

test('手动新建画布置于列表首位并进入画布，创建期间重复点击不重复请求', async () => {
  const { descriptor } = parse(readFileSync(new URL('../src/views/Canvas.vue', import.meta.url), 'utf8'))
  const script = ts.createSourceFile('canvas.ts', descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true)
  const functions = script.statements.filter(statement => ts.isFunctionDeclaration(statement) && ['newBoard', 'enterBoard'].includes(statement.name.text))
  const state = { homeMode: ref(true), boards: ref([{ id: 12 }]), loading: ref(false), creating: ref(false), submitting: new Set(), uploadBusy: ref(false), chatBusy: ref(false) }
  const opened = []
  let finishCreate
  let creates = 0
  const api = loadScript(functions.map(fn => fn.getText(script)).join('\n'), {
    ...state, persist: async () => {},
    createCanvas: () => { creates++; return new Promise(resolve => { finishCreate = resolve }) },
    openBoard: async id => { opened.push(id); return true },
    ElMessage: { error: error => assert.fail(error) }, message: String,
  }, ['newBoard'])
  const pending = api.newBoard()
  await Promise.resolve()
  await api.newBoard()
  assert.equal(creates, 1)
  finishCreate({ id: 23, name: '新画布' })
  await pending
  assert.deepEqual(state.boards.value.map(board => board.id), [23, 12])
  assert.deepEqual(opened, [23])
  assert.equal(state.homeMode.value, false)
  assert.equal(state.creating.value, false)
})

test('未选画布首次任务自动创建，后续消息复用当前画布', async () => {
  const entry = canvasEntry()
  assert.equal(await entry.prepareChatCanvas(), 23)
  assert.equal(await entry.prepareChatCanvas(), 23)
  assert.deepEqual(entry.calls, ['创建', ['打开', 23], '保存', '保存'])
  assert.equal(entry.homeMode.value, false)
  assert.equal(entry.chatPanelOpen.value, true)
})

test('选择已有画布时不创建，创建后的加载失败重试也不会重复创建', async () => {
  const chosen = canvasEntry()
  chosen.homeCanvasId.value = 12
  await chosen.prepareChatCanvas()
  assert.deepEqual(chosen.calls, [['打开', 12], '保存'])

  let opens = 0
  const retry = canvasEntry({ openBoard: async () => ++opens > 1 })
  await assert.rejects(retry.prepareChatCanvas(), /画布加载失败/)
  assert.equal(retry.homeMode.value, true)
  await retry.prepareChatCanvas()
  assert.equal(retry.calls.filter(call => call === '创建').length, 1)
})

test('空名称不提交，重命名和删除只操作菜单选中的画布', async () => {
  const calls = []
  const panel = panelWithStream(async () => response, {
    defineProps: () => ({
      renameCanvas: async (id, name) => { calls.push(['重命名', id, name]) },
      deleteCanvas: async id => { calls.push(['删除', id]) },
    }),
  })
  const board = { id: 45, name: '旧名称' }
  panel.openCanvasDialog('rename', board)
  panel.canvasName.value = '   '
  await panel.confirmCanvasDialog()
  assert.equal(panel.canvasDialogError.value, '请输入画布名称')
  assert.deepEqual(calls, [])
  panel.canvasName.value = '  新名称  '
  await panel.confirmCanvasDialog()
  assert.deepEqual(calls, [['重命名', 45, '新名称']])
  assert.equal(panel.canvasDialog.value, undefined)
  panel.openCanvasDialog('delete', board)
  assert.equal(calls.length, 1)
  await panel.confirmCanvasDialog()
  assert.deepEqual(calls.at(-1), ['删除', 45])
})

test('重命名失败保留弹窗和错误，允许再次提交', async () => {
  const panel = panelWithStream(async () => response, {
    defineProps: () => ({ renameCanvas: async () => { throw new Error('名称保存失败') } }),
  })
  panel.openCanvasDialog('rename', { id: 45, name: '旧名称' })
  panel.canvasName.value = '新名称'
  await panel.confirmCanvasDialog()
  assert.equal(panel.canvasDialog.value.type, 'rename')
  assert.equal(panel.canvasName.value, '新名称')
  assert.equal(panel.canvasDialogError.value, '名称保存失败')
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
  }, ['entries', 'toolState', 'toolError', 'skillEvent'])
}

test('技能状态通过流式接口到达界面，并与模型步骤分开展示', async () => {
  const skill = { type: 'skill_call', skill_id: 'seedance-prompt', status: 'loaded', instruction_chars: 200, message: '已加载技能规则，将用于本轮模型请求' }
  const model = { type: 'model_request', round: 1, model: 'selected-model', message_count: 3, tools: [] }
  const panel = panelWithStream(apiWithEvents([['trace', skill], ['trace', model], ['done', response]]))
  await panel.handleSubmit(submission)
  const trace = executionTrace(panel.messages.value.at(-1).events)
  assert.deepEqual(trace.entries.value.map(entry => entry.event.type), ['skill_call', 'model_request'])
  assert.deepEqual(trace.skillEvent.value, skill)
  const skipped = { ...skill, skill_id: null, status: 'skipped', instruction_chars: 0, message: '未选择技能，使用通用提示词优化' }
  assert.deepEqual(executionTrace([skipped, model]).skillEvent.value, skipped)
  assert.equal(executionTrace([model]).skillEvent.value, undefined)
})

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
