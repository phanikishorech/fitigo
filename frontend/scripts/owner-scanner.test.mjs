import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import jsQR from 'jsqr'
const source = readFileSync(new URL('../src/components/accessQrMatrix.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { accessQrMatrix } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
for (const inverted of [false, true]) test(`jsQR decodes existing customer access QR (${inverted ? 'inverted' : 'normal'}) without BarcodeDetector`, () => {
  const token = 'GYMACCESS:scanner-fixture-not-valid', width = 328, scale = 8
  const data = new Uint8ClampedArray(width * width * 4)
  for(let i=0;i<data.length;i+=4){data[i]=data[i+1]=data[i+2]=inverted?0:255;data[i+3]=255}
  accessQrMatrix(token).forEach((row,y)=>row.forEach((dark,x)=>{if(dark)for(let dy=0;dy<scale;dy++)for(let dx=0;dx<scale;dx++){const i=(((y+4)*scale+dy)*width+(x+4)*scale+dx)*4;data[i]=data[i+1]=data[i+2]=inverted?255:0}}))
  assert.equal(jsQR(data,width,width,{inversionAttempts:'attemptBoth'})?.data,token)
})
test('blank camera frames are not treated as access tokens',()=>{
  assert.equal(jsQR(new Uint8ClampedArray(160*160*4).fill(255),160,160),null)
})