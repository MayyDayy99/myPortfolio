// Pixel crabs, drawn as terminal Raster cells: two pixels per cell, stacked
// with half-block characters, so an 8x4 sprite takes 8 columns and 2 rows.

const DEFAULT = 0x01000000
const UPPER = 0x2580 // ▀
const LOWER = 0x2584 // ▄
const SPACE = 0x20

const PALETTE: Record<string, number> = {
  o: 0xe8743b, // shell
  e: 0x1a1a1a, // eyes
  g: 0x3fb27f, // shell, finished
}

// Two walking frames: claws and legs swap each step.
const FRAMES = [
  ['o.o..o.o', '.oeooeo.', '.oooooo.', 'o.o..o.o'],
  ['.oo..oo.', '.oeooeo.', '.oooooo.', '.o.oo.o.'],
]

export const CRAB_WIDTH = 8
export const CRAB_ROWS = 2

type Pixels = { width: number; height: number; color: number[] }

const blank = (width: number, height: number): Pixels => ({
  width,
  height,
  color: new Array(width * height).fill(DEFAULT),
})

const stamp = (into: Pixels, frame: number, x: number, isDone: boolean) => {
  const sprite = FRAMES[frame % FRAMES.length] ?? FRAMES[0] ?? []
  sprite.forEach((line, y) => {
    for (let dx = 0; dx < line.length; dx++) {
      const ch = line[dx]
      const px = x + dx
      if (ch === '.' || px < 0 || px >= into.width || y >= into.height) continue
      into.color[y * into.width + px] = PALETTE[isDone && ch === 'o' ? 'g' : (ch ?? 'o')] ?? DEFAULT
    }
  })
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

const toBase64 = (bytes: Uint8Array): string => {
  let out = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const n = ((bytes[i] ?? 0) << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0)
    out += B64.charAt((n >> 18) & 63) + B64.charAt((n >> 12) & 63)
    out += i + 1 < bytes.length ? B64.charAt((n >> 6) & 63) : '='
    out += i + 2 < bytes.length ? B64.charAt(n & 63) : '='
  }
  return out
}

// Packs pixel rows in pairs into Raster cells: [codePoint, fg, bg] as LE u32.
const toCells = (p: Pixels): string => {
  const rows = Math.ceil(p.height / 2)
  const words = new Uint32Array(p.width * rows * 3)
  for (let row = 0; row < rows; row++) {
    for (let x = 0; x < p.width; x++) {
      const top = p.color[2 * row * p.width + x] ?? DEFAULT
      const bottom = 2 * row + 1 < p.height ? (p.color[(2 * row + 1) * p.width + x] ?? DEFAULT) : DEFAULT
      const at = (row * p.width + x) * 3
      if (top === DEFAULT && bottom === DEFAULT) {
        words.set([SPACE, DEFAULT, DEFAULT], at)
      } else if (top === DEFAULT) {
        words.set([LOWER, bottom, DEFAULT], at)
      } else {
        words.set([UPPER, top, bottom], at)
      }
    }
  }
  return toBase64(new Uint8Array(words.buffer))
}

/** One crab, for a row of the panel. */
export const crabCells = (frame: number, isDone: boolean): string => {
  const p = blank(CRAB_WIDTH, 4)
  stamp(p, frame, 0, isDone)
  return toCells(p)
}

/**
 * A lane `width` columns wide where one crab per running agent walks back
 * and forth; each crab starts at its own offset so they spread out.
 */
export const laneCells = (width: number, crabs: number, frame: number): string => {
  const p = blank(width, 4)
  const span = Math.max(1, width - CRAB_WIDTH)
  for (let i = 0; i < crabs; i++) {
    const t = (frame + i * 11) % (2 * span)
    const x = t < span ? t : 2 * span - t
    stamp(p, frame + i, x, false)
  }
  return toCells(p)
}
