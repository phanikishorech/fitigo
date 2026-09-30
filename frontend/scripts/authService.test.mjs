import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/services/authService.ts', import.meta.url), 'utf8')
  .replace("import { ApiError, post } from './client'", `
    class ApiError extends Error { constructor(message, status) { super(message); this.status = status } }
    const post = (path, body) => globalThis.__authTestPost(path, body, ApiError);
  `)
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { authService } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('password login uses the existing endpoint, normalizes email, preserves password', async () => {
  const tokens = { access_token: 'test-access', refresh_token: 'test-refresh', token_type: 'bearer' }
  globalThis.__authTestPost = async (path, body) => {
    assert.equal(path, '/auth/login')
    assert.deepEqual(body, { email: 'member@example.com', password: ' Case Sensitive Password ' })
    return tokens
  }
  assert.deepEqual(await authService.loginWithPassword(' Member@Example.com ', ' Case Sensitive Password '), tokens)
})
test('wrong password is not described as an expired session', async () => {
  globalThis.__authTestPost = async (_path, _body, ApiError) => { throw new ApiError('Your session has expired.', 401) }
  await assert.rejects(authService.loginWithPassword('member@example.com', 'incorrect'), error => error.status === 401 && error.message === 'The email or password is incorrect. Please try again.')
})
test('network and rate-limit errors preserve retry guidance', async () => {
  for (const status of [0, 429, 500]) {
    globalThis.__authTestPost = async (_path, _body, ApiError) => { throw new ApiError('Please try again later.', status) }
    await assert.rejects(authService.loginWithPassword('member@example.com', 'test'), error => error.status === status && error.message === 'Please try again later.')
  }
})
test('email and mobile OTP endpoints are unchanged', async () => {
  const calls = []
  globalThis.__authTestPost = async (path, body) => { calls.push({ path, body }); return {} }
  await authService.sendEmail('member@example.com')
  await authService.verifyEmail('member@example.com', '123456')
  await authService.sendMobile('+91', '9000000000')
  await authService.verifyMobile('+91', '9000000000', '123456')
  assert.deepEqual(calls.map(call => call.path), ['/auth/email/send-otp', '/auth/email/verify-otp', '/auth/mobile/send-otp', '/auth/mobile/verify-otp'])
  assert.deepEqual(calls[3].body, { country_code: '+91', mobile_number: '9000000000', otp: '123456' })
})