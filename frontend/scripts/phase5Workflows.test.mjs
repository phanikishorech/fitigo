import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL('../src/'+path,import.meta.url),'utf8')
const compiled=ts.transpileModule(read('utils/paymentInstructions.ts'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const {paymentInstructions}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
for(const provider of ['CASHFREE','RAZORPAY','WALLET_TEST_CREDIT','DISABLED'])test(`payment instructions follow backend ${provider}`,()=>{
 const text=paymentInstructions({checkout_available:provider!=='DISABLED',payment_mode:provider})
 if(provider==='CASHFREE')assert.match(text,/Cashfree.*server verification/)
 if(provider==='RAZORPAY')assert.match(text,/Razorpay.*server verification/)
 if(provider==='WALLET_TEST_CREDIT')assert.match(text,/not real-money/)
 if(provider==='DISABLED')assert.match(text,/unavailable/)
})
test('unknown payment method is not represented as wallet or live',()=>{
 assert.match(paymentInstructions({checkout_available:true}),/backend-confirmed/)
})
test('booking UI uses server capability list and reasons',()=>{
 assert.match(read('owner/services.ts'),/return booking.allowed_actions \?\? \[\]/)
 assert.match(read('owner/Bookings.tsx'),/action_unavailable_reasons/)
 assert.match(read('owner/Bookings.tsx'),/Open QR check-in/)
})
test('help and settings distinguish unsupported workflows',()=>{
 assert.match(read('owner/Account.tsx'),/owners may scan for their own gyms/)
 assert.doesNotMatch(read('owner/Account.tsx'),/Owner permissions alone do not grant/)
 assert.match(read('owner/Account.tsx'),/Cancellation does not automatically refund/)
 assert.match(read('owner/Account.tsx'),/NotificationCenter inbox=\{false\}/)
 assert.match(read('components/common/NotificationCenter.tsx'),/not enabled in this deployment/)
 assert.match(read('admin/WorkflowSettings.tsx'),/not a complete platform audit log/)
})
test('profile uses existing authenticated endpoint and honors reauthentication',()=>{
 const source=read('components/common/AccountProfileEditor.tsx')
 assert.match(source,/await profileService.update/)
 assert.match(source,/result.reauthenticate/)
 assert.match(source,/clearTokens\(\)/)
 assert.match(source,/await restoreSession/)
 assert.ok(source.indexOf('setSaved(true)')>source.indexOf('await profileService.update'))
})