import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
globalThis.__staffReact = React
const source = readFileSync(new URL('../src/owner/StaffIdentity.tsx', import.meta.url), 'utf8')
const code = ts.transpileModule(source
  .replace(/import \{ istDateTime \}[^\r\n]+/, `const React=globalThis.__staffReact;const istDateTime=()=> '20 Oct 2026, 15:30 IST';`)
  .replace(/import \{ StatusBadge \}[^\r\n]+/, `const StatusBadge=({status})=>React.createElement('span',null,status);`),
  { compilerOptions: { jsx: ts.JsxEmit.React, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { default: StaffIdentity, staffName } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const staff = { id: 393, user_id: 6, gym_id: 1, role: 'STAFF', first_name: 'Kiran', last_name: 'Trainer', email: 'kiran@example.com', phone: '+919999999999', account_status: 'ACTIVE', assigned_at: '2026-10-20T10:00:00Z' }

test('staff card displays identity, contact information, status and assigned date', () => {
  const html = renderToStaticMarkup(React.createElement(StaffIdentity, { staff }))
  for (const text of ['Kiran Trainer', 'kiran@example.com', '+919999999999', 'ACTIVE', 'STAFF', '20 Oct 2026', 'Assignment #393', 'Staff #6']) assert.ok(html.includes(text), text)
})
test('missing staff fields use honest fallbacks, not invented information', () => {
  assert.equal(staffName({ ...staff, first_name: null, last_name: null }), staff.email)
  const missing = { ...staff, first_name: null, last_name: null, email: null, phone: null, account_status: null, assigned_at: null }
  assert.equal(staffName(missing), 'Staff #6')
  const html = renderToStaticMarkup(React.createElement(StaffIdentity, { staff: missing }))
  for (const text of ['Not provided', 'Account unavailable', 'Not recorded']) assert.ok(html.includes(text))
})
test('staff names are rendered as text and removal confirmation identifies the person', () => {
  const html = renderToStaticMarkup(React.createElement(StaffIdentity, { staff: { ...staff, first_name: '<script>alert(1)</script>' } }))
  assert.ok(!html.includes('<script>'))
  const operations = readFileSync(new URL('../src/owner/Operations.tsx', import.meta.url), 'utf8')
  assert.match(operations, /StaffIdentity staff=\{s\}/)
  assert.match(operations, /staffName\(remove\)/)
  assert.doesNotMatch(operations, /Only staff IDs|Names, invitation delivery/)
})