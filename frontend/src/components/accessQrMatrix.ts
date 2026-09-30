// QR Model 2, version 4-L, byte mode, mask 0. One Reed–Solomon block.
// Fixed capacity is intentional: our opaque ASCII access tokens fit in 78 bytes.
export function accessQrMatrix(value: string): boolean[][] {
  const bytes = new TextEncoder().encode(value)
  if (bytes.length > 78) throw new Error('Access token exceeds QR capacity')
  const bits: number[] = []
  const append = (value: number, count: number) => {
    for (let i = count - 1; i >= 0; i--) bits.push((value >>> i) & 1)
  }
  append(4, 4)
  append(bytes.length, 8)
  bytes.forEach((b) => append(b, 8))
  append(0, Math.min(4, 640 - bits.length))
  while (bits.length % 8) bits.push(0)
  const data: number[] = []
  for (let i = 0; i < bits.length; i += 8) data.push(bits.slice(i, i + 8).reduce((a, b) => a * 2 + b, 0))
  for (let i = 0; data.length < 80; i++) data.push(i % 2 ? 0x11 : 0xec)
  const multiply = (a: number, b: number) => {
    let result = 0
    for (; b; b >>>= 1) {
      if (b & 1) result ^= a
      a <<= 1
      if (a & 0x100) a ^= 0x11d
    }
    return result
  }
  let generator = [1]
  let root = 1
  for (let i = 0; i < 20; i++) {
    const next = Array(generator.length + 1).fill(0) as number[]
    generator.forEach((c, j) => { next[j] ^= c; next[j + 1] ^= multiply(c, root) })
    generator = next
    root = multiply(root, 2)
  }
  const remainder = [...data, ...Array(20).fill(0)] as number[]
  for (let i = 0; i < 80; i++) {
    const factor = remainder[i]
    generator.forEach((c, j) => { remainder[i + j] ^= multiply(c, factor) })
  }
  const payload = [...data, ...remainder.slice(80)].flatMap((b) => Array.from({ length: 8 }, (_, i) => (b >>> (7 - i)) & 1))
  const size = 33
  const matrix = Array.from({ length: size }, () => Array<boolean>(size).fill(false))
  const reserved = Array.from({ length: size }, () => Array<boolean>(size).fill(false))
  const set = (x: number, y: number, dark: boolean) => {
    if (x < 0 || y < 0 || x >= size || y >= size) return
    matrix[y][x] = dark
    reserved[y][x] = true
  }
  for (const [cx, cy] of [[3, 3], [29, 3], [3, 29]]) {
    for (let y = -4; y <= 4; y++) for (let x = -4; x <= 4; x++) {
      const distance = Math.max(Math.abs(x), Math.abs(y))
      set(cx + x, cy + y, distance !== 2 && distance !== 4)
    }
  }
  for (let i = 8; i < 25; i++) { set(i, 6, i % 2 === 0); set(6, i, i % 2 === 0) }
  for (let y = -2; y <= 2; y++) for (let x = -2; x <= 2; x++) set(26 + x, 26 + y, Math.max(Math.abs(x), Math.abs(y)) !== 1)
  const format = 0x77c4 // BCH-encoded level L, mask 0, XOR 0x5412
  const bit = (i: number) => ((format >>> i) & 1) !== 0
  for (let i = 0; i <= 5; i++) set(8, i, bit(i))
  set(8, 7, bit(6)); set(8, 8, bit(7)); set(7, 8, bit(8))
  for (let i = 9; i < 15; i++) set(14 - i, 8, bit(i))
  for (let i = 0; i < 8; i++) set(size - 1 - i, 8, bit(i))
  for (let i = 8; i < 15; i++) set(8, size - 15 + i, bit(i))
  set(8, size - 8, true)
  let index = 0
  let up = true
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5
    for (let row = 0; row < size; row++) {
      const y = up ? size - 1 - row : row
      for (let j = 0; j < 2; j++) {
        const x = right - j
        if (!reserved[y][x]) matrix[y][x] = Boolean((payload[index++] ?? 0) ^ ((x + y) % 2 === 0 ? 1 : 0))
      }
    }
    up = !up
  }
  return matrix
}