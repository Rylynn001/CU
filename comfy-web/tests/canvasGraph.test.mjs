import test from 'node:test'
import assert from 'node:assert/strict'
import { makeNode, validConnection, collectInputs, canvasReferences } from '../src/services/canvasGraph.ts'

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

test('按入边展示生成节点的参考缩略图，并为图片和视频分别编号', () => {
  const image = makeNode('remote-imageNode', { x: 0, y: 0 })
  const video = makeNode('remote-videoNode', { x: 0, y: 200 })
  const target = makeNode('remote-videoGenerationNode', { x: 500, y: 0 })
  image.data.outputs.image = { dataType: 'IMAGE', value: { assetIds: [21, 22] } }
  video.data.outputs.video = { dataType: 'VIDEO', value: { assetIds: [31] } }
  const refs = canvasReferences([image, video, target], {
    21: { id: 21, url: '/21.png', type: 'image' },
    22: { id: 22, url: '/22.png', type: 'image' },
    31: { id: 31, url: '/31.mp4', type: 'video' },
  }, [
    { id: 'i', source: image.id, sourceHandle: 'image', target: target.id, targetHandle: 'in' },
    { id: 'v', source: video.id, sourceHandle: 'video', target: target.id, targetHandle: 'in' },
  ], target.id)
  assert.deepEqual(refs.map(item => item.mention), ['@图片1', '@图片2', '@视频1'])
  assert.deepEqual(refs.map(item => item.url), ['/21.png', '/22.png', '/31.mp4'])
})
