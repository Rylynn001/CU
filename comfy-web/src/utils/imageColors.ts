const RGB_COLOR_COUNT = 1 << 24

export interface ImageColor {
  /** Hexadecimal RGB value, for example `#3a71c4`. */
  hex: string
  /** Packed 24-bit RGB value. Useful for fast comparisons. */
  rgb: number
  /** Number of pixels with this exact RGB value. */
  pixels: number
  /** Share of the analyzed pixels, in the range 0–100. */
  percentage: number
}

export interface ColorAnalysis {
  colors: ImageColor[]
  totalPixels: number
  analyzedPixels: number
  transparentPixels: number
  uniqueColors: number
}

export interface ColorAnalysisOptions {
  /** Pixels with a lower alpha value are ignored. Defaults to 1. */
  minimumAlpha?: number
  /** Limits returned colors after exact counting and sorting. Defaults to every color. */
  maxColors?: number
}

let histogram: Uint32Array | undefined

function getHistogram() {
  histogram ??= new Uint32Array(RGB_COLOR_COUNT)
  return histogram
}

function toHex(rgb: number) {
  return `#${rgb.toString(16).padStart(6, '0')}`
}

/**
 * Extracts exact RGB color proportions with a single pixel scan.
 *
 * The 24-bit histogram is allocated once and reused between calls. Only colors
 * that actually occur are collected and sorted, so repeated analysis avoids
 * object allocation during the hot pixel-processing loop.
 */
export function analyzeImageColors(source: ImageData | Uint8ClampedArray, options: ColorAnalysisOptions = {}): ColorAnalysis {
  const data = source.data ?? source
  const minimumAlpha = Math.min(255, Math.max(0, options.minimumAlpha ?? 1))
  const totalPixels = data.length >>> 2
  const counts = getHistogram()
  const usedColors = new Uint32Array(totalPixels)
  let usedColorCount = 0
  let analyzedPixels = 0

  try {
    for (let index = 0; index < data.length; index += 4) {
      if (data[index + 3] < minimumAlpha) continue

      const rgb = (data[index] << 16) | (data[index + 1] << 8) | data[index + 2]
      if (counts[rgb]++ === 0) usedColors[usedColorCount++] = rgb
      analyzedPixels++
    }

    const colors = new Array<ImageColor>(usedColorCount)
    for (let index = 0; index < usedColorCount; index++) {
      const rgb = usedColors[index]
      const pixels = counts[rgb]
      colors[index] = { rgb, hex: toHex(rgb), pixels, percentage: analyzedPixels ? pixels / analyzedPixels * 100 : 0 }
    }

    colors.sort((left, right) => right.pixels - left.pixels || left.rgb - right.rgb)
    const maxColors = Math.max(0, options.maxColors ?? colors.length)

    return {
      colors: maxColors < colors.length ? colors.slice(0, maxColors) : colors,
      totalPixels,
      analyzedPixels,
      transparentPixels: totalPixels - analyzedPixels,
      uniqueColors: usedColorCount,
    }
  } finally {
    for (let index = 0; index < usedColorCount; index++) counts[usedColors[index]] = 0
  }
}

/** Returns the combined share of colors within an RGB distance of the target. */
export function getColorPercentage(analysis: ColorAnalysis, targetRgb: number, tolerance = 42) {
  if (!analysis.analyzedPixels) return 0

  const red = targetRgb >> 16
  const green = (targetRgb >> 8) & 255
  const blue = targetRgb & 255
  const maxDistanceSquared = tolerance * tolerance
  let pixels = 0

  for (const color of analysis.colors) {
    const colorRed = color.rgb >> 16
    const colorGreen = (color.rgb >> 8) & 255
    const colorBlue = color.rgb & 255
    const distanceSquared = (colorRed - red) ** 2 + (colorGreen - green) ** 2 + (colorBlue - blue) ** 2
    if (distanceSquared <= maxDistanceSquared) pixels += color.pixels
  }

  return pixels / analysis.analyzedPixels * 100
}

/**
 * Merges nearby RGB values into 4-bit color buckets and returns the strongest
 * representative colors. This avoids treating minor lighting variations as
 * different dominant colors.
 */
export function getDominantColors(analysis: ColorAnalysis, limit = 5): ImageColor[] {
  if (!analysis.analyzedPixels || limit <= 0) return []

  const buckets = new Map<number, { red: number; green: number; blue: number; pixels: number }>()
  for (const color of analysis.colors) {
    const red = color.rgb >> 16
    const green = (color.rgb >> 8) & 255
    const blue = color.rgb & 255
    const bucketId = (red >> 4 << 8) | (green >> 4 << 4) | (blue >> 4)
    const bucket = buckets.get(bucketId)
    if (bucket) {
      bucket.red += red * color.pixels
      bucket.green += green * color.pixels
      bucket.blue += blue * color.pixels
      bucket.pixels += color.pixels
    } else {
      buckets.set(bucketId, { red: red * color.pixels, green: green * color.pixels, blue: blue * color.pixels, pixels: color.pixels })
    }
  }

  return [...buckets.values()]
    .sort((left, right) => right.pixels - left.pixels)
    .slice(0, limit)
    .map(bucket => {
      const rgb = (Math.round(bucket.red / bucket.pixels) << 16) | (Math.round(bucket.green / bucket.pixels) << 8) | Math.round(bucket.blue / bucket.pixels)
      return { rgb, hex: toHex(rgb), pixels: bucket.pixels, percentage: bucket.pixels / analysis.analyzedPixels * 100 }
    })
}
