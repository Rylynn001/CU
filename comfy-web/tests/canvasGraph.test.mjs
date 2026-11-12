import test from 'node:test'
import assert from 'node:assert/strict'
import { makeNode, validConnection, collectInputs } from '../src/services/canvasGraph.ts'

test('端口类型限制参考素材，拒绝自连接、重复连接和环路', () => {
  const image = makeNode('remote-imageGenerationNode', { x: 0, y: 0 })
  const video = makeNode('remote-videoGenerationNode', { x: 400, y: 0 })
  const nodes = [image, video]
  const connection = { source: image.id, sourceHandle: 'image', target: video.id, targetHandle: 'in' }
  assert.equal(validConnection(connection, nodes, []), true)
  assert.equal(validConnection({ ...connection, source: video.id, sourceHandle: 'video', target: image.id }, nodes, []), false)
  assert.equal(validConnection({ ...connection, target: image.id }, nodes, []), false)
  assert.equal(validConnection(connection, nodes, [{ ...connection, id: 'existing' }]), false)
  assert.equal(validConnection({ ...connection, id: 'existing' }, nodes, [{ ...connection, id: 'existing' }]), true)
  const second = makeNode('remote-imageGenerationNode', { x: 800, y: 0 })
  assert.equal(validConnection({ source: second.id, sourceHandle: 'image', target: image.id, targetHandle: 'in' }, [...nodes, second], [{ id: 'forward', source: image.id, sourceHandle: 'image', target: second.id, targetHandle: 'in' }]), false)
})

test('文本及多个参考资产转换为现有生成接口输入，资产去重且保序', () => {
  const text = makeNode('remote-textNode', { x: 0, y: 0 })
  const image = makeNode('remote-imageNode', { x: 0, y: 200 })
  const video = makeNode('remote-videoGenerationNode', { x: 500, y: 0 })
  text.data.outputs.text = { dataType: 'STRING', value: '小鸟飞翔' }
  image.data.outputs.image = { dataType: 'IMAGE', value: { assetIds: [12, 13, 12] } }
  const edges = [
    { id: 'text', source: text.id, sourceHandle: 'text', target: video.id, targetHandle: 'in' },
    { id: 'image', source: image.id, sourceHandle: 'image', target: video.id, targetHandle: 'in' },
  ]
  assert.deepEqual(collectInputs(video.id, [text, image, video], edges), { assetIds: [12, 13], texts: ['小鸟飞翔'] })
  assert.equal(JSON.stringify(image.data).includes('url'), false)
  image.data.task = { taskId: 'running', historyId: 1, state: 'pending' }
  assert.throws(() => collectInputs(video.id, [text, image, video], edges), /正在生成/)
  delete image.data.task
  image.data.outputs = {}
  assert.throws(() => collectInputs(video.id, [text, image, video], edges), /暂无输出/)
})
