import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
async function load(path, transform = s => s) {
  const js = ts.transpileModule(transform(readFileSync(new URL(path, import.meta.url), 'utf8')), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)
}
globalThis.__returnCustomer = await load('../src/customerRoutes.ts')
globalThis.__returnOwner = await load('../src/owner/routes.ts')
globalThis.__returnAdmin = await load('../src/admin/routes.ts')
const routes = s => s.replace(/import .* from '..\/customerRoutes'/, 'const {customerRoute,isProtectedRoute}=globalThis.__returnCustomer')
  .replace(/import .* from '..\/owner\/routes'/, 'const {ownerRoute}=globalThis.__returnOwner')
  .replace(/import .* from '..\/admin\/routes'/, 'const {adminRoute}=globalThis.__returnAdmin')
globalThis.__returnPolicy = await load('../src/session/policy.ts', routes)
globalThis.__returnActions = await load('../src/session/pendingActions.ts', routes)
const data = new Map()
globalThis.sessionStorage = { getItem: k => data.get(k) ?? null, setItem: (k,v) => data.set(k,v), removeItem: k => data.delete(k) }
globalThis.window = { location: { pathname: '/login', search: '', hash: '' } }
let destination = null
globalThis.__returnNavigate = to => { destination = to; const url = new URL(to, 'https://fitigo.test'); window.location = { pathname:url.pathname, search:url.search, hash:url.hash } }
const service = await load('../src/session/returnIntent.ts', s => s
  .replace(/import .* from '.\/policy'/, 'const {canOpen,isReturnableRoute,roleHome,routePolicy}=globalThis.__returnPolicy')
  .replace(/import .* from '.\/pendingActions'/, 'const {canResumeAction,validatePendingAction}=globalThis.__returnActions')
  .replace(/import .* from '..\/router'/, 'const navigate=globalThis.__returnNavigate'))
const identity = (role, id=1) => ({ user:{id}, roles:[role] })
const reset = () => { service.clearReturnIntent(); globalThis.__returnNavigate('/login'); destination=null }
for (const [role, path] of [['CUSTOMER','/gyms/123?tab=membership#plans'],['USER','/membership/5/details'],['CUSTOMER','/gyms/1/book/schedule?type=CLASS'],['GYM_OWNER','/owner/revenue?gym=4#monthly'],['GYM_STAFF','/owner/check-in'],['ADMIN','/admin/settings#security'],['SUPER_ADMIN','/admin/users?page=2']]) {
  test(`${role} restores exact authorized location ${path}`, () => {
    reset(); const intent=service.saveReturnIntent(service.validateReturnPath(path)); const before=JSON.parse([...data.values()][0])
    assert.equal(before.phase,'login');service.handlePostLoginRedirect(identity(role));assert.equal(destination,path)
    assert.ok(service.consumeReturnIntent(intent.id,identity(role)));assert.equal(service.getReturnIntent(),null)
    assert.equal(service.consumeReturnIntent(intent.id,identity(role)),null)
  })
}
test('safe fallback for cross-role and staff-restricted routes; no replay', () => {
  for (const [role,path,home] of [['CUSTOMER','/admin/settings','/home'],['GYM_OWNER','/admin/users','/owner/dashboard'],['GYM_STAFF','/owner/revenue','/owner/dashboard']]) {
    reset();service.saveReturnIntent(service.validateReturnPath(path));service.handlePostLoginRedirect(identity(role));assert.equal(destination,home);assert.equal(service.getReturnIntent(),null)
  }
})
test('login with no intent uses role home', () => {
  for(const role of ['CUSTOMER','USER','GYM_OWNER','GYM_STAFF','ADMIN','SUPER_ADMIN']){reset();service.handlePostLoginRedirect(identity(role));assert.equal(destination,__returnPolicy.roleHome([role]))}
})
test('rejects external, normalization, encoding, unknown and authentication-loop destinations', () => {
  for(const path of ['https://evil.test','//evil.test','/\\evil.test','/owner/../admin/settings','/%2f%2fevil.test','/gyms/%31','/home\n','/login','/auth/reset-password?token=secret','/owner/verify','/admin/session-expired','/owner/reports','/not-real','/home?token=secret','/home#access_token=secret','/home?email=person@example.test']) assert.equal(service.validateReturnPath(path),null,path)
})
test('pending action is generic, validates identifiers and claims once after route restoration', () => {
  for(const [action,path,metadata,role] of [['BOOK_VISIT','/gyms/9?tab=membership#plans',{gymId:'9'},'CUSTOMER'],['ADD_TO_CART','/gyms/9/book/schedule',{gymId:'9'},'CUSTOMER'],['VIEW_REPORT','/owner/revenue',{},'GYM_OWNER'],['EDIT_GYM','/owner/gyms/9/edit',{gymId:'9'},'GYM_OWNER']]) {
    reset();const intent=service.saveReturnIntent({...service.validateReturnPath(path),action,metadata});assert.equal(intent.action,action)
    service.handlePostLoginRedirect(identity(role));assert.equal(service.consumeReturnIntent(intent.id,identity(role)).action,action)
    assert.equal(service.consumeReturnIntent(intent.id,identity(role)),null)
  }
})
test('unregistered/unsafe action or sensitive metadata restores page only', () => {
  for(const input of [{action:'PAYMENT',metadata:{amount:'100'}},{action:'BOOK_VISIT',metadata:{gymId:'7'}},{action:'BOOK_VISIT',metadata:{gymId:'9',password:'secret'}}]) {
    reset();const intent=service.saveReturnIntent({pathname:'/gyms/9',search:'',hash:'',...input});assert.equal(intent.action,null);assert.deepEqual(intent.metadata,{})
    assert.equal([...data.values()][0].includes('secret'),false)
  }
})
test('expired, future-dated, malformed and different-account intents are not resumed', () => {
  for(const change of [i=>({...i,createdAt:Date.now()-31*60*1000}),i=>({...i,createdAt:Date.now()+100000}),i=>({...i,pathname:'//evil.test'})]) {
    reset();service.saveReturnIntent({pathname:'/membership',search:'',hash:''});const key=[...data.keys()][0];data.set(key,JSON.stringify(change(JSON.parse(data.get(key)))));assert.equal(service.getReturnIntent(),null)
  }
  reset();service.saveReturnIntent({pathname:'/membership',search:'',hash:''});const key=[...data.keys()][0];data.set(key,'{ broken');assert.equal(service.getReturnIntent(),null)
  reset();service.saveReturnIntent({pathname:'/membership',search:'',hash:''});service.handlePostLoginRedirect(identity('CUSTOMER'));globalThis.__returnNavigate('/login');service.handlePostLoginRedirect(identity('CUSTOMER',2));assert.equal(destination,'/home')
})
test('login returnTo works for every portal, rejects external value, no redirect loop', () => {
  reset();globalThis.__returnNavigate('/login?returnTo=%2Fadmin%2Fsettings%3Ftab%3Dsecurity%23password');service.handlePostLoginRedirect(identity('ADMIN'));assert.equal(destination,'/admin/settings?tab=security#password')
  reset();globalThis.__returnNavigate('/login?returnTo=https%3A%2F%2Fevil.test');service.handlePostLoginRedirect(identity('ADMIN'));assert.equal(destination,'/admin/dashboard')
})
test('expiration capture preserves a pending action without overwriting it at login', () => {
  reset();globalThis.__returnNavigate('/gyms/9?tab=membership#plans');service.requestAuthentication({action:'BOOK_VISIT',metadata:{gymId:'9'}})
  const first=service.getReturnIntent();assert.equal(destination,'/login');service.requestAuthentication({},true);assert.equal(service.getReturnIntent().id,first.id)
  service.handlePostLoginRedirect(identity('CUSTOMER'));assert.equal(destination,'/gyms/9?tab=membership#plans')
})