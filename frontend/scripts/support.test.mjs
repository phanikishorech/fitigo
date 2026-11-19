import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')
const code = ts.transpileModule(read('admin/routes.ts'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const routes = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
test('support and readiness routes remain within protected admin portal', () => {
  assert.equal(routes.adminRoute('/admin/support').page, 'notFound')
  assert.equal(routes.adminRoute('/admin/readiness').page, 'notFound')
  assert.equal(routes.adminRoute('/admin/support/garbage').page, 'notFound')
  assert.match(read('session/policy.ts'), /portal: 'admin', protected: true/)
})
test('support saves use stable retry keys and backend version checks', () => {
  const source = read('components/common/SupportRequests.tsx')
  assert.match(source, /Idempotency-Key/)
  assert.match(source, /expected_version: version/)
  assert.match(source, /current.payload/)
  assert.match(source, /resource.data.can_change_status/)
  assert.match(source, /resource.data.can_reply/)
  assert.match(source, /Your draft is retained/)
  assert.doesNotMatch(source, /dangerouslySetInnerHTML/)
})
test('unsupported support deployment and manual readiness never appear successful', () => {
  assert.match(read('components/common/SupportRequests.tsx'), /No request has been submitted/)
  assert.match(read('admin/Readiness.tsx'), /does not certify production readiness/)
  assert.match(read('admin/Readiness.tsx'), /Manual acceptance checks remain required/)
  assert.match(read('components/common/SupportRequests.tsx'), /No attachments, email delivery or response-time promise/)
})