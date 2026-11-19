import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

async function component(path) {
  const source = `import React from 'react';\n${readFileSync(new URL(path, import.meta.url), 'utf8')}`
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React } }).outputText
    .replace('import React from \'react\';', 'const React = globalThis.__financialReact;')
  globalThis.__financialReact = React
  return (await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)).default
}
const RevenueScope = await component('../src/admin/RevenueScope.tsx')
const CancellationNotice = await component('../src/components/common/CancellationNotice.tsx')
test('admin financial scope is explicit and unknown mode is not silently live', () => {
  for (const [mode, text] of [['test', 'No real money'], ['live', 'Test payments excluded'], [undefined, 'scope unavailable']]) {
    const html = renderToStaticMarkup(React.createElement(RevenueScope, { mode }))
    assert.ok(html.includes(text))
    assert.ok(html.includes('scheduled booking date'))
    assert.ok(html.includes('Cancelled/no-show bookings remain included while paid'))
    assert.ok(html.includes('Booking counts cover all modes'))
  }
})
test('cancellation notice limits credit to eligible wallet-only cancellations and not arbitrary overrides', () => {
  const html = renderToStaticMarkup(React.createElement(CancellationNotice))
  assert.ok(html.includes('at least 3 hours before the scheduled start'))
  assert.ok(html.includes('credit FitiGo Wallet, not the original payment method'))
  assert.ok(html.includes('Administrative overrides do not authorize arbitrary credits'))
  assert.ok(html.includes('review the recorded cancellation result'))
})