import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
async function load(path, transform = s => s) {
  const source = transform(read(path))
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
}
const { customerRoute, isProtectedRoute } = await load('../src/customerRoutes.ts')
const { profileService, walletService } = await load('../src/services/accountService.ts', s => s.replace(/import \{ post, request \}[^\r\n]+/, `const request=(...args)=>globalThis.__accountRequest(...args);const post=(...args)=>request(...args);`))
test('customer payment history is an authenticated route', () => {
  assert.deepEqual(customerRoute('/profile/payments'), { page: 'payments' })
  assert.equal(isProtectedRoute(customerRoute('/profile/payments')), true)
})
test('profile editor uses authenticated update and legacy wallet cannot mint credits', async () => {
  let call; globalThis.__accountRequest = async (...args) => { call = args; return {} }
  const payload = { first_name: 'Name', last_name: 'Last', email: 'name@example.com', phone: null }
  await profileService.update(payload)
  assert.equal(call[0], '/users/me'); assert.equal(call[1].method, 'PATCH'); assert.deepEqual(JSON.parse(call[1].body), payload)
  await assert.rejects(walletService.recharge(100), /secure gateway checkout/)
})
test('wallet recharge reuses gateway component and never calls direct credit endpoint', () => {
  const wallet = read('../src/pages/wallet/WalletPage.tsx')
  assert.match(wallet, /GatewayPayment/); assert.match(wallet, /WALLET_TOPUP/)
  assert.doesNotMatch(wallet, /walletService.recharge|MVP wallet credit|\/wallet\/topup/)
})
test('payment history exposes order/attempt/refund IDs with server pagination', () => {
  const history = read('../src/pages/profile/PaymentHistory.tsx')
  for (const term of ['provider_order_id', 'transaction_id', 'refunded_amount', 'paymentService.refresh', '/payments/history?', 'offset']) assert.ok(history.includes(term))
  assert.doesNotMatch(history, /payment_session_id|KEY_SECRET|CLIENT_SECRET/)
  assert.doesNotMatch(history, /WALLET_LEDGER|Gateway purchases and wallet ledger entries/)
  assert.match(history, /Cancel unpaid payment/)
  assert.match(history, /paymentService.cancel/)
})
test('settings reuse password change and require current password for contacts', () => {
  const settings = read('../src/pages/profile/SettingsPage.tsx')
  assert.match(settings, /NewPasswordForm change/); assert.match(settings, /current_password/)
  assert.match(settings, /unverified/); assert.match(settings, /clearTokens/)
})