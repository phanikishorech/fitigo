import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
globalThis.policyReact = React
const source = readFileSync(new URL('../src/admin/PolicyContractEditor.tsx', import.meta.url), 'utf8')
  .replace(/^import .*$/gm, '')
const code = ts.transpileModule(`const React=globalThis.policyReact;\n${source}`, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React } }).outputText
const { SchemaFields } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
test('nullable singleton policy remains an explicit selectable choice, not auto-configured', () => {
  const schema = { anyOf: [{ const: 'VERIFIED_BACKEND_CHECKIN', type: 'string' }, { type: 'null' }] }
  const html = renderToStaticMarkup(React.createElement(SchemaFields, { schema, root: schema, value: null, onChange() {}, path: 'attended.eligibility' }))
  assert.match(html, /<select/); assert.match(html, /value="" selected=""/)
  assert.match(html, /Not configured/); assert.match(html, /VERIFIED_BACKEND_CHECKIN/)
})
test('null monetary policy is not rendered as a zero amount', () => {
  const schema = { anyOf: [{ type: 'number', minimum: 0 }, { type: 'string' }, { type: 'null' }] }
  const html = renderToStaticMarkup(React.createElement(SchemaFields, { schema, root: schema, value: null, onChange() {}, path: 'multi_gym.platform_monthly_payout_cap' }))
  assert.match(html, /value=""/); assert.match(html, /step="0.01"/); assert.doesNotMatch(html, /value="0"/)
})
test('explicit empty deductions differ from unconfigured deductions', () => {
  const schema = { anyOf: [{ type: 'array', items: { enum: ['ACTUAL_GATEWAY_FEES'] } }, { type: 'null' }] }
  const render = value => renderToStaticMarkup(React.createElement(SchemaFields, { schema, root: schema, value, onChange() {}, path: 'settlements.eligible_deductions' }))
  assert.doesNotMatch(render(null), /checked=""/)
  assert.match(render([]), /checked=""/)
})
test('policy editor uses server schema and validation, not financial calculations', () => {
  assert.match(source, /catalog.schema/); assert.match(source, /validatePolicy/)
  assert.match(source, /structuredClone\(catalog.empty\)/)
  assert.match(source, /Posting eligibility: blocked/)
  assert.doesNotMatch(source, /calculateCommission|postJournal|85\.00|70\.00/)
})