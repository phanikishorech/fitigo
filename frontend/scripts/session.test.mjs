import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
async function load(path,transform=s=>s){const src=transform(readFileSync(new URL(path,import.meta.url),'utf8'));const js=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;return import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`)}
const customer=await load('../src/customerRoutes.ts'), owner=await load('../src/owner/routes.ts')
globalThis.__sessionAdmin=await load('../src/admin/routes.ts')
globalThis.__sessionCustomer=customer;globalThis.__sessionOwner=owner
const policy=await load('../src/session/policy.ts',s=>s.replace(/import .* from '..\/customerRoutes'/,'const {customerRoute,isProtectedRoute}=globalThis.__sessionCustomer').replace(/import .* from '..\/owner\/routes'/,'const {ownerRoute}=globalThis.__sessionOwner').replace(/import .* from '..\/admin\/routes'/,'const {adminRoute}=globalThis.__sessionAdmin'))
globalThis.__rolePolicy=policy
let token=null, reason='signedOut', nav=null, handler=null, respond, requests=0
globalThis.__sessionAuth={getAccessToken:()=>token,getAuthReason:()=>reason,setTokens:t=>{token=t;handler?.()},clearTokens:r=>{token=null;reason=r||'signedOut';handler?.()},subscribeAuth:h=>{handler=h;return()=>{handler=null}}}
globalThis.__sessionRequest=(...args)=>{requests++;return respond(...args)}
globalThis.__sessionNavigate=(...args)=>{nav=args}
globalThis.window={addEventListener(){},removeEventListener(){},location:{pathname:'/login',search:'',hash:''}}
globalThis.localStorage={getItem:()=> 'fixture-refresh'}
const store=await load('../src/session/store.ts',s=>s
 .replace(/import .* from '..\/auth'/,'const {clearTokens,getAccessToken,getAuthReason,setTokens,subscribeAuth}=globalThis.__sessionAuth')
 .replace(/import .* from '..\/services\/client'/,'class ApiError extends Error{constructor(message,status){super(message);this.status=status}};globalThis.__SessionError=ApiError;const request=(...args)=>globalThis.__sessionRequest(...args)')
 .replace(/import .* from '..\/services\/readCache'/,'const clearReadCache=()=>{}')
 .replace(/import .* from '..\/router'/,'const navigate=(...args)=>globalThis.__sessionNavigate(...args)')
 .replace(/import .* from '.\/returnIntent'/,'const clearReturnIntent=()=>{},currentLocation=()=>window.location,saveReturnIntent=()=>{},handlePostLoginRedirect=i=>globalThis.__sessionNavigate(globalThis.__rolePolicy.roleHome(i.roles),true)')
 .replace(/import .* from '.\/policy'/,'const {backendRoles,roleHome,routePolicy}=globalThis.__rolePolicy'))
const identity=roles=>({user:{id:1,email:'same@example.com',first_name:'User',last_name:null,phone:null,status:'ACTIVE'},roles})
for(const [role,home] of Object.entries({CUSTOMER:'/home',USER:'/home',GYM_OWNER:'/owner/dashboard',GYM_STAFF:'/owner/dashboard',ADMIN:'/admin/dashboard',SUPER_ADMIN:'/admin/dashboard'}))test(`backend ${role} uses existing home and blocks other portals`,()=>{
 assert.equal(policy.roleHome([role]),home)
 for(const route of ['/home','/membership','/owner/dashboard','/admin/dashboard'])assert.equal(policy.canOpen([role],route),home==='/home'?route==='/home'||route==='/membership':route===home)
})
test('staff retains limited workspace permissions; assigned multiple roles are respected',()=>{
 assert.equal(policy.canOpen(['GYM_STAFF'],'/owner/gyms/1/edit'),false)
 for(const route of ['/owner/check-in','/owner/settings','/staff/check-in'])assert.equal(policy.canOpen(['GYM_STAFF'],route),true)
 assert.equal(policy.canOpen(['CUSTOMER','GYM_OWNER'],'/membership'),true)
 assert.equal(policy.canOpen(['CUSTOMER','GYM_OWNER'],'/owner/gyms/1'),true)
 assert.equal(policy.roleHome(['CUSTOMER','GYM_OWNER']),'/owner/dashboard')
 assert.equal(policy.roleHome(['GYM_OWNER','ADMIN']),'/admin/dashboard')
})
test('public discovery retained, protected booking/customer/workspace routes guarded',()=>{
 for(const route of ['/home','/explore','/gyms/1','/auth/forgot-password','/auth/reset-password'])assert.equal(policy.routePolicy(route).protected,false,route)
 for(const route of ['/cart','/membership','/profile','/wallet','/gyms/1/book/access','/owner/gyms','/admin/users'])assert.equal(policy.routePolicy(route).protected,true,route)
 for(const route of ['/login','/auth/login','/admin/login','/owner/login'])assert.equal(policy.routePolicy(route).login,true)
})
test('missing, unknown and malformed roles never default to customer',()=>{
 for(const roles of [null,undefined,[],['unknown'],['ADMIN','unknown'],'ADMIN',[null]])assert.equal(policy.backendRoles(roles),null)
 assert.equal(policy.roleHome([]),null)
})
test('login redirects from response roles, not login URL or supplied user email',async()=>{
 for(const role of ['CUSTOMER','USER','GYM_OWNER','GYM_STAFF','ADMIN','SUPER_ADMIN']){
  requests=0;nav=null
  await store.completeLogin({access_token:'token-'+role,refresh_token:'refresh',...identity([role])})
  assert.equal(store.getSession().status,'authenticated')
  assert.deepEqual(nav,[policy.roleHome([role]),true]);assert.equal(requests,0)
 }
})
test('refresh restores current backend roles and shares in-flight verification',async()=>{
 token='restored';requests=0;let resolve;respond=()=>new Promise(r=>{resolve=r})
 const a=store.restoreSession(),b=store.restoreSession()
 assert.equal(store.getSession().status,'loading');assert.equal(requests,1);assert.equal(a,b)
 resolve(identity(['GYM_OWNER']));await a;assert.deepEqual(store.getSession().identity.roles,['GYM_OWNER'])
})
test('network/server errors retain token and retry; 403 is forbidden, not anonymous',async()=>{
 for(const status of [0,500,403]){
  token='retained';respond=async()=>{throw new globalThis.__SessionError('failure',status)}
  await store.restoreSession();assert.equal(token,'retained');assert.equal(store.getSession().status,status===403?'forbidden':'error')
  respond=async()=>identity(['CUSTOMER']);await store.restoreSession();assert.equal(store.getSession().status,'authenticated')
 }
})
test('missing roles are distinct from API failure; valid retry can recover',async()=>{
 token='missing';respond=async()=>identity([]);await store.restoreSession();assert.equal(store.getSession().status,'invalid-role')
 respond=async()=>({roles:['ADMIN'],user:null});await store.restoreSession();assert.equal(store.getSession().status,'error')
})
test('old session request cannot overwrite a newer login',async()=>{
 token='old';let resolve;respond=()=>new Promise(r=>{resolve=r});const old=store.restoreSession()
 await store.completeLogin({access_token:'new',refresh_token:'refresh',...identity(['GYM_OWNER'])})
 resolve(identity(['ADMIN']));await old;assert.deepEqual(store.getSession().identity.roles,['GYM_OWNER'])
})
test('logout clears role/token state and navigates to /login even offline',async()=>{
 respond=async()=>{throw new Error('offline')};await store.logoutSession()
 assert.equal(token,null);assert.equal(store.getSession().status,'anonymous');assert.deepEqual(nav,['/login',true])
 reason='expired';await store.restoreSession();assert.equal(store.getSession().status,'expired')
})