// TEST ONLY: backend session fixtures, no real credentials/accounts are changed.
import assert from 'node:assert/strict'
const origin='http://localhost:5173',debug='http://localhost:9231'
// Separate storage from other open fixture tabs: cross-tab logout is now real behavior.
const browserInfo=await(await fetch(`${debug}/json/version`)).json()
const browser=new WebSocket(browserInfo.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{browser.onopen=resolve;browser.onerror=reject})
let browserSequence=0;const browserPending=new Map()
browser.onmessage=event=>{const m=JSON.parse(event.data);const p=browserPending.get(m.id);if(p){browserPending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}}
function browserCommand(method,params={}){return new Promise((resolve,reject)=>{const id=++browserSequence;browserPending.set(id,{resolve,reject});browser.send(JSON.stringify({id,method,params}))})}
const {browserContextId}=await browserCommand('Target.createBrowserContext')
const {targetId}=await browserCommand('Target.createTarget',{url:'about:blank',browserContextId})
const target=(await(await fetch(`${debug}/json`)).json()).find(t=>t.id===targetId)
const ws=new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
let sequence=0,roles=['CUSTOMER'],failure=null,loginFailure=false,sessionDelay=0,logoutFailure=false
let membershipIncluded = true
let addedItems = []
const pending=new Map(),errors=[],calls=[]
const user={id:1,first_name:'Same',last_name:'Account',email:'same@example.com',phone:null,status:'ACTIVE',created_at:'2026-09-30T00:00:00Z'}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(Error(method)),20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms))
async function until(expression){for(let i=0;i<120;i++){if(await evaluate(expression))return;await wait(100)}throw Error(`Not ready: ${expression}; ${await evaluate('document.body?.innerText')}`)}
async function click(text,selector='button'){await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`);await wait(70)}
async function fill(selector,value){await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`);await wait(40)}
async function visit(path){await command('Page.navigate',{url:origin+path});await wait(250)}
async function reloadForLogin(){await evaluate(`window.__returnReloadMarker=true`);await command('Page.reload');await until(`typeof window.__returnReloadMarker==='undefined' && document.readyState==='complete'`);await wait(200)}
const home=role=>['ADMIN','SUPER_ADMIN'].includes(role)?'/admin/dashboard':['GYM_OWNER','GYM_STAFF'].includes(role)?'/owner/dashboard':'/home'
async function atHome(role){await until(`location.pathname===${JSON.stringify(home(role))} && !!document.querySelector(${JSON.stringify(home(role)==='/home'?'.fg-hero':role==='GYM_STAFF'?'.ow-main':home(role)==='/owner/dashboard'?'.ow-metric-grid':'.ad-metrics')})`)}
ws.onmessage=async event=>{
 const m=JSON.parse(event.data)
 if(pending.has(m.id)){const p=pending.get(m.id);clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
 if(m.method==='Fetch.requestPaused'){
  const {requestId,request}=m.params;const path=new URL(request.url).pathname;calls.push(path)
  try{
   let body={},code=200
   if(path==='/api/v1/auth/session'){
    await wait(sessionDelay)
    if(failure===0){await command('Fetch.failRequest',{requestId,errorReason:'ConnectionFailed'});return}
    code=failure||200;body=failure?{detail:'Private SQL exception'}:{user,roles}
   }else if(path==='/api/v1/auth/login'){
    code=loginFailure?401:200;body=loginFailure?{detail:'Invalid credentials'}:{access_token:'fixture-role-token',refresh_token:'fixture-refresh',token_type:'bearer',user,roles}
   }else if(path==='/api/v1/auth/logout'){
    if(logoutFailure){await command('Fetch.failRequest',{requestId,errorReason:'ConnectionFailed'});return}
    body={status:'ok'}
   }else if(path==='/api/v1/users/me')body=user
   else if(path==='/api/v1/users/me/roles')body=roles
   else if(path==='/api/v1/gyms/discover')body={gyms:[],page:1,page_size:8,total_count:0,has_more:false}
   else if(['/api/v1/meta/gym-types','/api/v1/facilities','/api/v1/gym-owner/gyms','/api/v1/gym-staff/gyms','/api/v1/admin/gyms','/api/v1/admin/bookings','/api/v1/admin/reports/bookings/daily'].includes(path))body=[]
   else if(path==='/api/v1/gym-owner/dashboard/summary')body={gyms:{total:0,approved:0,pending_approval:0,draft:0},bookings:{today:0,upcoming:0},revenue:{last_30d:'0.00',currency:'INR'}}
   else if(path==='/api/v1/admin/dashboard/summary')body={users:{total:0,customers:0,gym_owners:0},gyms:{total:0,pending_approval:0},bookings:{today:0,upcoming:0},revenue:{last_30d:'0.00',currency:'INR'}}
   else if(path==='/api/v1/profile')body={user_id:1,full_name:'Same Account',profile_image:null,member_since:user.created_at,membership_status:null}
   else if(path==='/api/v1/auth/password-reset/options')body={email_available:false}
   else if(path==='/api/v1/memberships/me')body=[]
   else if(path==='/api/v1/profile/membership')body={membership_id:null,plan_name:null,status:null,start_date:null,end_date:null,membership_scope:null,active_gyms:[],membership_features:[]}
   else if(path==='/api/v1/customer/access-calendar')body={access_type:'MULTI_GYM',gym:null,days:[{date:new Date().toISOString().slice(0,10),status:'TODAY',qr_available:true,qr_status:'ACTIVE',gym_name:null,checkin_time:null}]}
   else if(path==='/api/v1/gyms/1/details')body={gym_id:1,gym_name:'Return fixture gym',slug:'return-fixture',location:{locality:'Test district',city:'Test city',full_address:'Test address'},ratings:{average_rating:null,review_count:0},images:[],opening_hours:{open_now:true,open_today:'06:00 – 22:00',weekly:[]},workout_options:[],amenities:[],description:'Test-only gym',important_information:[],rules:[],membership_access:{status:membershipIncluded?'INCLUDED':'NO_ACTIVE_MEMBERSHIP',upgrade_required:false,day_pass_available:true},classes_nearby:[],related_gyms:[],reviews:[]}
   else if(path==='/api/v1/gyms/1/booking-options')body={gym_id:1,gym_name:'Return fixture gym',membership_status:{status:'NO_ACTIVE_MEMBERSHIP',title:'Day visit',tone:'info'},available_access_types:[],workout_areas:[],gym_price_per_person:'425.00',has_classes:false}
   else if(path==='/api/v1/gyms/1/operating-hours')body={gym_id:1,date:new Date().toISOString().slice(0,10),day_of_week:1,open_time:'06:00:00',close_time:'22:00:00',is_closed:false}
   else if(path==='/api/v1/cart/items/gym' && request.method==='POST'){
    const item=JSON.parse(request.postData);addedItems.push(item);body={...item,id:1,status:'ACTIVE',price_per_person:'425.00',total_price:'425.00',currency:'INR',gym_name:'Return fixture gym'}
   }
   else if(path==='/api/v1/cart/items')body=[]
   else if(path==='/api/v1/wallet/balance')body={balance:'1000.00',currency:'INR'}
   else throw Error(`Unexpected API ${path}`)
   await command('Fetch.fulfillRequest',{requestId,responseCode:code,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
  }catch(e){if(e.message.includes('Invalid InterceptionId'))return;errors.push(e.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'}).catch(()=>{})}
 }
}
try{
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await visit('/login');await until(`document.body?.innerText.includes('Welcome to FitiGo')`)
 for(const role of ['CUSTOMER','USER','GYM_OWNER','GYM_STAFF','ADMIN','SUPER_ADMIN']){
  roles=[role];await evaluate(`localStorage.clear()`);await visit('/login');await until(`!!document.querySelector('[role="dialog"]')`)
  await click('Password');await fill('input[name="email"]',user.email);await fill('input[name="password"]','fixture-password')
  await click('Sign in with password');await atHome(role)
  for(const path of ['/login','/owner/login','/admin/login','/auth/login']){await visit(path);await atHome(role)}
  const forbidden=home(role)==='/home'?['/owner/gyms','/admin/users']:home(role)==='/admin/dashboard'?['/profile','/owner/gyms']:['/profile','/admin/users']
  if(role==='GYM_STAFF')forbidden.push('/owner/gyms')
  for(const path of forbidden){const before=calls.length;await visit(path);await atHome(role);assert.equal(calls.slice(before).some(p=>p==='/api/v1/admin/users'||p==='/api/v1/profile'),false)}
  await command('Page.reload');await atHome(role)
  assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),'fixture-role-token')
 }
 console.log('PASS all six backend roles: login response routing, existing homes, login aliases, cross-role guards and refresh')
 for(const entry of ['/owner/login','/admin/login']){
  roles=['CUSTOMER'];await evaluate('localStorage.clear()');await visit(entry)
  await until(`!!document.querySelector('input[name="email"]')`)
  await fill('input[name="email"]',user.email);await fill('input[name="password"]','fixture-password')
  await click(entry.startsWith('/admin')?'Sign In':'Sign in');await atHome('CUSTOMER')
 }
 await evaluate('localStorage.clear()');await visit('/login');await until(`!!document.querySelector('[role="dialog"]')`)
 await click('Password');await fill('input[name="email"]',user.email);await fill('input[name="password"]','wrong');loginFailure=true
 await click('Sign in with password');await until(`document.body.innerText.includes('email or password is incorrect')`)
 assert.equal(await evaluate('location.pathname'),'/login');loginFailure=false
 for(const path of ['/cart','/owner/gyms','/admin/users']){await visit(path);await until(`location.pathname==='/login' && !!document.querySelector('[role="dialog"]')`)}
 console.log('PASS wrong-portal login uses actual role; incorrect credentials remain inline; anonymous protected routes go to /login')
 for(const status of [0,500,403,401]){
  roles=['GYM_OWNER'];await evaluate(`localStorage.setItem('fitigo:access_token','restore-token')`);failure=status;await visit('/owner/settings')
  if(status===401){await until(`location.pathname==='/login' && location.search.includes('expired=1')`);assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),null)}
  else {
   await until(`document.body?.innerText.includes(${JSON.stringify(status===403?'Access denied':'Unable to verify your session')})`)
   assert.equal(await evaluate('location.pathname'),'/owner/settings');assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),'restore-token')
   failure=null;await click(status===403?'Check again':'Try Again');await until(`document.body.innerText.includes('Owner profile')`)
  }
  failure=null
 }
 for(const invalid of [[],['UNKNOWN'],['ADMIN','UNKNOWN']]){
  roles=invalid;await evaluate(`localStorage.setItem('fitigo:access_token','invalid-role-token')`);await visit('/login');await until(`document.body?.innerText.includes('no supported role')`)
  assert.equal(await evaluate('location.pathname'),'/login')
 }
 roles=['GYM_STAFF'];sessionDelay=1200;await evaluate(`localStorage.setItem('fitigo:access_token','loading-token')`);await visit('/owner/settings')
 await until(`!!document.querySelector('[aria-label="Loading"]')`);assert.equal(await evaluate(`!!document.querySelector('.ow-main')`),false)
 await until(`document.body.innerText.includes('Owner profile')`);sessionDelay=0
 // Cross-tab logout notification follows the same centralized path.
 await evaluate(`localStorage.removeItem('fitigo:access_token');window.dispatchEvent(new StorageEvent('storage',{key:'fitigo:access_token'}))`)
 await until(`location.pathname==='/login'`)
 console.log('PASS network/server/expired/forbidden/invalid-role/loading states, retries and cross-tab logout')
 for(const role of ['CUSTOMER','GYM_OWNER','GYM_STAFF','ADMIN']){
  roles=[role];await evaluate(`localStorage.setItem('fitigo:access_token','logout-token');localStorage.setItem('fitigo:refresh_token','logout-refresh')`)
  await visit(role==='CUSTOMER'?'/profile':role==='ADMIN'?'/admin/dashboard':'/owner/settings')
  await until(`!!document.querySelector(${JSON.stringify(role==='ADMIN'?'.ad-metrics':role==='CUSTOMER'?'.fg-panel':'.ow-main')})`)
  logoutFailure=true
  await until(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()===${JSON.stringify(role==='ADMIN'?'Logout':'Sign out')})`)
  await click(role==='ADMIN'?'Logout':'Sign out')
  await until(`!!document.querySelector('dialog[open]')`);await click('Sign out','dialog button')
  await until(`location.pathname==='/login'`);assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),null);assert.equal(await evaluate(`localStorage.getItem('fitigo:refresh_token')`),null)
  logoutFailure=false
 }
 assert.deepEqual(errors,[])
 console.log('PASS all active logout UIs clear credentials and redirect /login even if server revocation fails')
 async function customerLogin(role) {
  roles=[role];await until(`!!document.querySelector('[role="dialog"]') && (Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Password') || !!document.querySelector('form[aria-label="Password sign in"]'))`)
  if(await evaluate(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Password')`))await click('Password')
  await until(`!!document.querySelector('form[aria-label="Password sign in"]')`)
  await fill('input[name="email"]',user.email);await fill('input[name="password"]','fixture-password');await click('Sign in with password')
 }
 async function anonymous() { await evaluate('localStorage.clear();sessionStorage.clear()');await command('Page.navigate',{url:'about:blank'});await until(`location.href==='about:blank'`) }
 for(const [role,path,marker] of [
  ['CUSTOMER','/membership?tab=history#records','Your next chapter starts here'],
  ['USER','/gyms/1/book/schedule?source=visit#schedule','Make time for yourself'],
  ['GYM_OWNER','/owner/revenue?period=month#report','Revenue'],
  ['GYM_STAFF','/owner/settings?tab=password#security','Owner profile'],
  ['ADMIN','/admin/settings?tab=security#password','Settings']
 ]) {
  await anonymous();await visit(path);await until(`location.pathname==='/login'`)
  assert.equal(await evaluate(`(()=>{const i=JSON.parse(sessionStorage.getItem('fitigo:return-intent:v1'));return i.pathname+i.search+i.hash})()`),path)
  await reloadForLogin();await customerLogin(role)
  await until(`location.pathname+location.search+location.hash===${JSON.stringify(path)} && document.body.innerText.includes(${JSON.stringify(marker)})`)
  await until(`sessionStorage.getItem('fitigo:return-intent:v1')===null`)
 }
 console.log('PASS customer membership/booking, owner report, staff settings, admin settings restore exact query/hash after login reload')
 // Public gym -> sign in returns to the same preview without triggering booking.
 await anonymous();await visit('/gyms/1?tab=membership#plans');await until(`document.body.innerText.includes('Book a Visit')`)
 await click('Sign in');await until(`location.pathname==='/login'`);await customerLogin('CUSTOMER')
 await until(`location.pathname+location.search+location.hash==='/gyms/1?tab=membership#plans' && document.body.innerText.includes('Book a Visit')`)
 assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`),false)
 // Generic handler continuation: backend decision, no new booking implementation.
 await anonymous();await visit('/gyms/1?tab=membership#plans');await until(`document.body.innerText.includes('Book a Visit')`)
 await click('Book a Visit');await until(`location.pathname==='/login'`)
 assert.equal(await evaluate(`JSON.parse(sessionStorage.getItem('fitigo:return-intent:v1')).action`),'BOOK_VISIT')
 await reloadForLogin();const beforeCalendar=calls.filter(p=>p==='/api/v1/customer/access-calendar').length
 await customerLogin('CUSTOMER');await until(`!!document.querySelector('dialog[open]')`)
 assert.equal(await evaluate(`location.pathname+location.search+location.hash`),'/gyms/1?tab=membership#plans')
 assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('dialog button')).map(b=>b.textContent.trim())`),['Use My Membership','Book for Others'])
 assert.equal(calls.filter(p=>p==='/api/v1/customer/access-calendar').length,beforeCalendar+1)
 assert.equal(await evaluate(`sessionStorage.getItem('fitigo:return-intent:v1')`),null)
 await command('Page.reload');await until(`document.body.innerText.includes('Book a Visit')`);await wait(300)
 assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`),false)
 membershipIncluded=false;await anonymous();await visit('/gyms/1');await until(`document.body.innerText.includes('Book a Visit')`);await click('Book a Visit');await customerLogin('CUSTOMER')
 await until(`location.pathname==='/gyms/1/book/access' && document.body.innerText.includes('How do you want to work out?')`);membershipIncluded=true
 console.log('PASS public gym continuation, BOOK_VISIT resumes once, refresh cannot replay, no-membership resumes normal booking')
 // A second registered action resumes its EXISTING handler, with draft data
 // staying in the existing draft store rather than in the return intent.
 await visit('/gyms/1/book/schedule');await until(`document.querySelectorAll('input[type="time"]').length===2 && !document.querySelector('[aria-label="Loading"]')`)
 await fill('input[type="time"]','09:00');await evaluate(`(()=>{const el=document.querySelectorAll('input[type="time"]')[1];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'10:00');el.dispatchEvent(new Event('input',{bubbles:true}))})()`);await wait(80)
 await evaluate(`localStorage.removeItem('fitigo:access_token')`)
 await click('Check availability & add to cart');await until(`location.pathname==='/login'`)
 assert.deepEqual(await evaluate(`JSON.parse(sessionStorage.getItem('fitigo:return-intent:v1')).metadata`),{gymId:'1'})
 await customerLogin('CUSTOMER');await until(`location.pathname==='/cart'`)
 assert.equal(addedItems.length,1);assert.equal(addedItems[0].gym_id,1)
 assert.equal(await evaluate(`sessionStorage.getItem('fitigo:return-intent:v1')`),null)
 console.log('PASS generic ADD_TO_CART handler reuses existing validated draft and service exactly once, no pricing/payment data persisted')
 for(const role of ['CUSTOMER','GYM_OWNER','GYM_STAFF']) {
  await anonymous();await visit('/admin/settings?tab=security');await customerLogin(role);await atHome(role)
  assert.equal(await evaluate(`sessionStorage.getItem('fitigo:return-intent:v1')`),null)
 }
 // Already authenticated login also consumes an authorized intent.
 roles=['ADMIN'];await evaluate(`localStorage.setItem('fitigo:access_token','fixture-authenticated');sessionStorage.clear()`)
 await visit('/login?returnTo=%2Fadmin%2Fsettings%3Ftab%3Dsecurity%23password');await until(`location.pathname+location.search+location.hash==='/admin/settings?tab=security#password'`)
 await until(`sessionStorage.getItem('fitigo:return-intent:v1')===null`)
 for(const value of ['https://evil.test','//evil.test','/login','/unknown','/owner/reports']){await visit('/login?returnTo='+encodeURIComponent(value));await atHome('ADMIN');assert.equal(await evaluate(`sessionStorage.getItem('fitigo:return-intent:v1')`),null)}
 // Expiry restores original location, not Home; a session failure does not consume intent.
 roles=['GYM_OWNER'];failure=401;await visit('/owner/settings?tab=password#security');await until(`location.pathname==='/login' && location.search.includes('expired=1')`);failure=null
 await customerLogin('GYM_OWNER');await until(`location.pathname+location.search+location.hash==='/owner/settings?tab=password#security' && document.body.innerText.includes('Owner profile')`)
 await until(`sessionStorage.getItem('fitigo:return-intent:v1')===null`)
 await anonymous();await visit('/membership');await until(`location.pathname==='/login'`)
 await evaluate(`localStorage.setItem('fitigo:access_token','restore-failure')`);failure=500;await command('Page.reload');await until(`document.body.innerText.includes('Unable to verify your session')`)
 assert.notEqual(await evaluate(`sessionStorage.getItem('fitigo:return-intent:v1')`),null);roles=['CUSTOMER'];failure=null;await click('Try Again');await until(`location.pathname==='/membership' && document.body.innerText.includes('Your next chapter starts here')`)
 await until(`sessionStorage.getItem('fitigo:return-intent:v1')===null`)
 assert.deepEqual(errors,[])
 console.log('PASS unauthorized fallback, authenticated login return, invalid/external URLs, expiration return, API-error retry preserves intent, no loops')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await browserCommand('Target.disposeBrowserContext',{browserContextId});browser.close()}