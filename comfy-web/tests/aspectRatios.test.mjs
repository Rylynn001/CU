import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { IMAGE_ASPECT_RATIOS, VIDEO_ASPECT_RATIOS, generationParameterFields, normalizeAspectRatioParameters } from '../src/constants/aspectRatios.ts'

test('图片和视频提供完整比例，每个矩形保持真实宽高比', () => {
  assert.deepEqual(IMAGE_ASPECT_RATIOS.map(item => item.value), ['1:1', '16:9', '9:16', '21:9', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', 'auto'])
  assert.deepEqual(VIDEO_ASPECT_RATIOS.map(item => item.value), ['16:9', '4:3', '1:1', '3:4', '9:16', '21:9', 'auto'])
  for (const item of [...IMAGE_ASPECT_RATIOS, ...VIDEO_ASPECT_RATIOS]) {
    if (item.value === 'auto') continue
    const [width, height] = item.value.split(':').map(Number)
    assert.equal(item.width * height, item.height * width)
  }
})

test('历史参数恢复真实比例并清除旧字段，显式比例优先', () => {
  assert.deepEqual(normalizeAspectRatioParameters('image', { size: '1536x1024', quality: 'high' }), { aspect_ratio: '3:2', quality: 'high' })
  assert.deepEqual(normalizeAspectRatioParameters('image', { size: '1792x768' }), { aspect_ratio: '21:9' })
  assert.deepEqual(normalizeAspectRatioParameters('image', { size: 'auto' }), { aspect_ratio: 'auto' })
  assert.deepEqual(normalizeAspectRatioParameters('video', { ratio: 'adaptive', duration: 8 }), { aspect_ratio: 'auto', duration: 8 })
  assert.deepEqual(normalizeAspectRatioParameters('image', { aspect_ratio: '4:3', size: 'auto', ratio: '1:1' }), { aspect_ratio: '4:3' })
  assert.throws(() => normalizeAspectRatioParameters('image', { size: 'wrong' }), /历史图片尺寸/)
})

test('模型切换仅展示一个比例字段，保留分辨率等其他参数', () => {
  const fields = generationParameterFields('image', [{ key: 'size' }, { key: 'ratio' }, { key: 'aspect_ratio' }, { key: 'image_size', default: '2K' }])
  assert.deepEqual(fields.map(field => field.key), ['aspect_ratio', 'image_size'])
  assert.equal(fields[0].options.length, 11)
  assert.equal(generationParameterFields('video')[0].options.length, 7)
})

test('三份 GPT 模型配置展示分辨率档位，并在历史恢复时保留选择', () => {
  for (const model of ['gpt-image-2', 'gpt-image-2.5-flare', 'gpt-image-2.5-sunburst']) {
    const config = JSON.parse(readFileSync(new URL(`../../background/docs/model_parameters/${model}.json`, import.meta.url), 'utf8'))
    const fields = generationParameterFields('image', config.fields)
    assert.deepEqual(fields.slice(0, 3).map(field => field.key), ['aspect_ratio', 'image_size', 'quality'])
    const resolution = fields.find(field => field.key === 'image_size')
    assert.equal(resolution.label, '分辨率')
    assert.equal(resolution.default, '1K')
    assert.deepEqual(resolution.options, ['1K', '2K', '4K', 'auto'])
    const defaults = Object.fromEntries(fields.map(field => [field.key, field.default]))
    const restored = { ...defaults, ...normalizeAspectRatioParameters('image', { aspect_ratio: '9:16', image_size: '4K' }) }
    assert.equal(restored.aspect_ratio, '9:16')
    assert.equal(restored.image_size, '4K')
  }
})
