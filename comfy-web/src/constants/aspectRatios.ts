import type { ApiModelParameterField } from '../api/apiService'

export interface AspectRatioOption {
  value: string
  label: string
  width: number
  height: number
}

const option = (value: string): AspectRatioOption => {
  const [width, height] = value.split(':').map(Number)
  return { value, label: value, width, height }
}

export const IMAGE_ASPECT_RATIOS: AspectRatioOption[] = [
  ...['1:1', '16:9', '9:16', '21:9', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4'].map(option),
  { value: 'auto', label: '自动', width: 4, height: 3 },
]

export const VIDEO_ASPECT_RATIOS: AspectRatioOption[] = [
  ...['16:9', '4:3', '1:1', '3:4', '9:16', '21:9'].map(option),
  { value: 'auto', label: '自动', width: 4, height: 3 },
]

export const IMAGE_ASPECT_RATIO_VALUES = IMAGE_ASPECT_RATIOS.map(option => option.value)
export const VIDEO_ASPECT_RATIO_VALUES = VIDEO_ASPECT_RATIOS.map(option => option.value)

export function generationParameterFields(mediaType: 'image' | 'video', fields: ApiModelParameterField[] = []): ApiModelParameterField[] {
  return [
    { key: 'aspect_ratio', label: '比例', type: 'select', default: mediaType === 'image' ? '1:1' : '16:9',
      options: mediaType === 'image' ? IMAGE_ASPECT_RATIO_VALUES : VIDEO_ASPECT_RATIO_VALUES },
    ...fields.filter(field => !['aspect_ratio', 'ratio', 'size'].includes(field.key)),
  ]
}

export function normalizeAspectRatioParameters(mediaType: 'image' | 'video', parameters: Record<string, string | number | boolean>) {
  const result = { ...parameters }
  let ratio: string | number | boolean | undefined = result.aspect_ratio ?? result.ratio
  if (ratio === undefined && result.size !== undefined) {
    const [width, height] = String(result.size).split('x').map(Number)
    ratio = result.size === 'auto' ? 'auto' : IMAGE_ASPECT_RATIOS.find(option =>
      option.value !== 'auto' && width * option.height === height * option.width)?.value
    if (ratio === undefined) throw new Error(`不支持的历史图片尺寸：${result.size}`)
  }
  result.aspect_ratio = ratio === 'adaptive' ? 'auto' : ratio ?? (mediaType === 'image' ? '1:1' : '16:9')
  delete result.ratio
  delete result.size
  return result
}
