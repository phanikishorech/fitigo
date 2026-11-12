import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

class ApiError extends Error {
  constructor(status, code) { super('Sanitized rejection'); this.status = status; this.code = code }
}
globalThis.__securityApiError = ApiError
const source = readFileSync(new URL('../src/owner/services.ts', import.meta.url), 'utf8')
  .replace(/import .* from '..\/services\/client'/,
    'const ApiError = globalThis.__securityApiError; const request = (...args) => globalThis.__securityRequest(...args); const post = request;')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { ownerService } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('scanner displays an explicit server authorization denial as a rejection', async () => {
  globalThis.__securityRequest = async () => { throw new ApiError(403, 'GYM_NOT_ALLOWED') }
  assert.deepEqual(await ownerService.checkIn(2, 'isolated-fixture'), {
    success: false, status: 'GYM_NOT_ALLOWED', message: 'Sanitized rejection'
  })
})

test('scanner does not disguise expired sessions, unknown denials or server failures', async () => {
  for (const error of [new ApiError(401), new ApiError(403), new ApiError(500), new Error('Network')]) {
    globalThis.__securityRequest = async () => { throw error }
    await assert.rejects(ownerService.checkIn(2, 'isolated-fixture'), candidate => candidate === error)
  }
})