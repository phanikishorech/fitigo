import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/components/accessQrMatrix.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText
const { accessQrMatrix } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

// Independently read version 4-L/mask 0 modules, then verify the payload and
// Reed–Solomon syndromes. No production encoder helpers are reused here.
function decode(matrix) {
  assert.equal(matrix.length, 33)
  matrix.forEach(row => assert.equal(row.length, 33))
  const reserved = (x, y) =>
    (x <= 8 && y <= 8) || (x >= 25 && y <= 8) || (x <= 8 && y >= 25) ||
    x === 6 || y === 6 || (x >= 24 && x <= 28 && y >= 24 && y <= 28)
  const bits = []
  let upwards = true
  for (let x = 32; x > 0; x -= 2) {
    if (x === 6) x--
    for (let i = 0; i < 33; i++) {
      const y = upwards ? 32 - i : i
      for (const col of [x, x - 1]) {
        if (!reserved(col, y)) bits.push(Number(matrix[y][col]) ^ Number((col + y) % 2 === 0))
      }
    }
    upwards = !upwards
  }
  assert.equal(bits.length, 807)
  assert.deepEqual(bits.slice(800), Array(7).fill(0))
  const number = (start, length) => bits.slice(start, start + length).reduce((a, b) => a * 2 + b, 0)
  assert.equal(number(0, 4), 4, 'byte mode')
  const count = number(4, 8)
  const bytes = Array.from({ length: count }, (_, i) => number(12 + i * 8, 8))
  const codewords = Array.from({ length: 100 }, (_, i) => number(i * 8, 8))
  const exp = [1]
  for (let i = 1; i < 255; i++) {
    const next = exp[i - 1] * 2
    exp.push(next > 255 ? next ^ 285 : next)
  }
  const log = new Map(exp.map((value, index) => [value, index]))
  for (let root = 0; root < 20; root++) {
    const syndrome = codewords.reduce((acc, word) =>
      (acc ? exp[(log.get(acc) + root) % 255] : 0) ^ word, 0)
    assert.equal(syndrome, 0, `error-correction root ${root}`)
  }
  const format = [0, 1, 2, 3, 4, 5, 7, 8].map(y => matrix[y][8])
    .concat([matrix[8][7]], [5, 4, 3, 2, 1, 0].map(x => matrix[8][x]))
  assert.equal(format.reduce((acc, bit, i) => acc | (Number(bit) << i), 0), 0x77c4)
  assert.equal(matrix[25][8], true, 'fixed dark module')
  return new TextDecoder().decode(Uint8Array.from(bytes))
}

for (const value of ['', 'GYMACCESS:' + 'a'.repeat(43), 'GYMACCESS:0123456789_-abcdefghijklmnopqrstuvwxyzABCDEFG', 'x'.repeat(78), 'é'.repeat(39)]) {
  test(`QR round-trip and error correction: ${new TextEncoder().encode(value).length} bytes`, () => {
    assert.equal(decode(accessQrMatrix(value)), value)
  })
}
test('capacity is enforced in bytes', () => {
  assert.throws(() => accessQrMatrix('x'.repeat(79)), /capacity/)
  assert.throws(() => accessQrMatrix('é'.repeat(40)), /capacity/)
})