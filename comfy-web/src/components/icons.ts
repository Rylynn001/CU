// Icon components using Heroicons or similar
// 这里使用简单的 SVG 组件

import { h, type FunctionalComponent } from 'vue'

interface IconProps {
  size?: number
  className?: string
}

export const ArrowUpIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 16, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M205.66,138.34a8,8,0,0,1-11.32,11.32L136,91.31V216a8,8,0,0,1-16,0V91.31L61.66,149.66a8,8,0,0,1-11.32-11.32l72-72a8,8,0,0,1,11.32,0Z',
      }),
    ]
  )
}

export const BrainIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 17, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M248,124a56.11,56.11,0,0,0-32-50.61V72a48,48,0,0,0-88-26.49A48,48,0,0,0,40,72v1.39a56,56,0,0,0,0,101.2V176a48,48,0,0,0,88,26.49A48,48,0,0,0,216,176v-1.41A56.09,56.09,0,0,0,248,124ZM88,208a32,32,0,0,1-31.81-28.56A55.87,55.87,0,0,0,64,180h8a8,8,0,0,0,0-16H64A40,40,0,0,1,50.67,86.27,8,8,0,0,0,56,78.73V72a32,32,0,0,1,64,0v68.26A47.8,47.8,0,0,0,88,128a8,8,0,0,0,0,16,32,32,0,0,1,0,64Zm104-40h-8a8,8,0,0,0,0,16h8a55.87,55.87,0,0,0,7.81-.56A32,32,0,1,1,168,144a8,8,0,0,0,0-16,47.8,47.8,0,0,0-32,12.26V72a32,32,0,0,1,64,0v6.73a8,8,0,0,0,5.33,7.54A40,40,0,0,1,192,164Z',
      }),
    ]
  )
}

export const PaperclipIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 16, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M209.66,122.34a8,8,0,0,1,0,11.32l-82.05,82a56,56,0,0,1-79.2-79.21L147.67,35.73a40,40,0,1,1,56.61,56.55L105,193A24,24,0,1,1,71,159L154.3,74.38A8,8,0,1,1,165.7,85.6L82.39,170.31a8,8,0,1,0,11.27,11.36L192.93,81A24,24,0,1,0,159,47L59.76,147.68a40,40,0,1,0,56.53,56.62l82.06-82A8,8,0,0,1,209.66,122.34Z',
      }),
    ]
  )
}

export const MicrophoneIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 16, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M128,176a48.05,48.05,0,0,0,48-48V64a48,48,0,0,0-96,0v64A48.05,48.05,0,0,0,128,176ZM96,64a32,32,0,0,1,64,0v64a32,32,0,0,1-64,0Zm40,143.6V232a8,8,0,0,1-16,0V207.6A80.11,80.11,0,0,1,48,128a8,8,0,0,1,16,0,64,64,0,0,0,128,0,8,8,0,0,1,16,0A80.11,80.11,0,0,1,136,207.6Z',
      }),
    ]
  )
}

export const MicrophoneFillIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 16, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M128,176a48.05,48.05,0,0,0,48-48V64a48,48,0,0,0-96,0v64A48.05,48.05,0,0,0,128,176Zm40,8a8,8,0,0,0-8,8,32,32,0,0,1-64,0,8,8,0,0,0-16,0,48.05,48.05,0,0,0,40,47.32V248a8,8,0,0,0,16,0V239.32A48.05,48.05,0,0,0,176,192,8,8,0,0,0,168,184Z',
      }),
    ]
  )
}

export const XIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 12, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M205.66,194.34a8,8,0,0,1-11.32,11.32L128,139.31,61.66,205.66a8,8,0,0,1-11.32-11.32L116.69,128,50.34,61.66A8,8,0,0,1,61.66,50.34L128,116.69l66.34-66.35a8,8,0,0,1,11.32,11.32L139.31,128Z',
      }),
    ]
  )
}

export const ImageIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 15, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M216,40H40A16,16,0,0,0,24,56V200a16,16,0,0,0,16,16H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40Zm0,16V158.75l-26.07-26.06a16,16,0,0,0-22.63,0l-20,20-44-44a16,16,0,0,0-22.62,0L40,149.37V56ZM40,172l52-52,80,80H40Zm176,28H194.63l-36-36,20-20L216,181.38V200ZM144,100a12,12,0,1,1,12,12A12,12,0,0,1,144,100Z',
      }),
    ]
  )
}

export const FileIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 15, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M213.66,82.34l-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40V216a16,16,0,0,0,16,16H200a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM160,51.31,188.69,80H160ZM200,216H56V40h88V88a8,8,0,0,0,8,8h48V216Z',
      }),
    ]
  )
}

export const GlobeIcon: FunctionalComponent<IconProps> = (props) => {
  const { size = 15, className = '' } = props
  return h(
    'svg',
    {
      width: size,
      height: size,
      viewBox: '0 0 256 256',
      fill: 'currentColor',
      class: className,
    },
    [
      h('path', {
        d: 'M128,24A104,104,0,1,0,232,128,104.11,104.11,0,0,0,128,24Zm88,104a87.62,87.62,0,0,1-6.4,32.94l-44.7-27.49a15.92,15.92,0,0,0-6.24-2.23l-22.82-3.08a16.11,16.11,0,0,0-16,7.86h-8.72l-3.8-7.86a15.91,15.91,0,0,0-11.23-8.25l-12.84-1.71a16,16,0,0,0-16.39,9L48.77,125A88,88,0,0,1,128,40a87.53,87.53,0,0,1,43.93,11.77l-8.5,34.07A16,16,0,0,0,168,105.51l23.07,12.66A16,16,0,0,0,198.86,121l9.91-8.93A88.68,88.68,0,0,1,216,128Z',
      }),
    ]
  )
}
