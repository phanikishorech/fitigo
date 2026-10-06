// Isolated auth fixtures. No real accounts, passwords, reset emails, or sessions are changed.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin='http://localhost:5173', debug='http://localhost:9231'
const target=await isolatedBrowserTarget(debug)
const ws=new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
const pending=new Map(), errors=[], calls=[]
let sequence=0, emailAvailable=true, mode='ok', roles=['CUSTOMER']
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(Error(method)),20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms))
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await wait(90)}throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`)}
async function click(text,selector='button'){await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`);await wait(80)}
async function fill(selector,value){await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`);await wait(35)}
async function visit(path,text){await command('Page.navigate',{url:origin+path});await until(`document.body?.innerText.includes(${JSON.stringify(text)})`)}
ws.onmessage=async event=>{
 const m=JSON.parse(event.data)
 if(pending.has(m.id)){const p=pending.get(m.id);clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
 if(m.method==='Fetch.requestPaused'){
  const {requestId,request}=m.params;const path=new URL(request.url).pathname;let body={},code=200
  try{
   if(request.method==='POST'){calls.push({path,body:JSON.parse(request.postData||'{}')});await wait(180)}
   if(path==='/api/v1/auth/register/customer'){body={id:1,email:'new@example.com'};if(mode==='duplicate'){code=409;body={detail:'Email already registered'}}}
   else if(path==='/api/v1/auth/login')body={access_token:'fixture-account-token',refresh_token:'fixture-refresh',token_type:'bearer'}
   else if(path==='/api/v1/auth/password-reset/options')body={email_available:emailAvailable}
   else if(path==='/api/v1/auth/forgot-password')body={message:'If an active account exists for this email, you will receive a password reset link.'}
   else if(path==='/api/v1/auth/reset-password'){body={status:'ok'};if(mode==='expired'){code=400;body={detail:'This reset link is invalid or expired. Request a new link.'}}}
   else if(path==='/api/v1/auth/change-password'){body={status:'ok'};if(mode==='wrong'){code=400;body={detail:'Your current password is incorrect.'}}}
    else if(path==='/api/v1/auth/session')body={user:{id:1,first_name:'Account',last_name:'Fixture',email:'new@example.com',phone:null},roles}
    else if(path==='/api/v1/gyms/discover')body={gyms:[],page:1,page_size:8,total_count:0,has_more:false}
    else if(path==='/api/v1/meta/gym-types'||path==='/api/v1/facilities')body=[]
    else if(path==='/api/v1/users/me')body={id:1,first_name:'Account',last_name:'Fixture',email:'new@example.com',phone:null}
   else if(path==='/api/v1/users/me/roles')body=roles
   else if(path==='/api/v1/gym-owner/gyms'||path==='/api/v1/gym-staff/gyms')body=[]
    else if(path==='/api/v1/memberships/me')body=[]
   else throw Error(`Unexpected API: ${path}`)
   await command('Fetch.fulfillRequest',{requestId,responseCode:code,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
  }catch(e){if(e.message.includes('Invalid InterceptionId'))return;errors.push(e.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'}).catch(()=>{})}
 }
}
try{
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await visit('/auth/login?returnTo=%2Fmembership%2Fpause','Welcome to FitiGo')
 await until(`!!document.querySelector('[role="dialog"]')`)
 await click('Password')
 async function checkModalScroll(label) {
  await evaluate(`(()=>{const d=document.querySelector('[role="dialog"]');window.scrollPanel=Array.from(d.children).find(el=>getComputedStyle(el).overflowY==='auto');window.scrollPanel.scrollTop=0})()`)
  const metrics=await evaluate(`(()=>{const p=window.scrollPanel,r=p.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+Math.min(120,r.height/2),overflow:p.scrollHeight>p.clientHeight,height:r.height,bottom:r.bottom,viewport:innerHeight}})()`)
  assert.ok(metrics.bottom<=metrics.viewport+1,`${label}: scroll panel fits viewport`)
  if(metrics.overflow){
    await command('Input.dispatchMouseEvent',{type:'mouseWheel',x:metrics.x,y:metrics.y,deltaY:1800,deltaX:0})
    await until(`window.scrollPanel.scrollTop>0`)
  }
  const result=await evaluate(`(()=>{const p=window.scrollPanel;p.scrollTop=p.scrollHeight;const buttons=Array.from(p.querySelectorAll('button'));const el=buttons.at(-1);const r=el.getBoundingClientRect(),bounds=p.getBoundingClientRect();return {visible:r.top>=bounds.top-1&&r.bottom<=bounds.bottom+1,hit:el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)),pageScroll:window.scrollY}})()`)
  assert.equal(result.visible,true,`${label}: bottom action visible`);assert.equal(result.hit,true,`${label}: bottom action is reachable`)
 }
 for(const [width,height] of [[360,640],[390,700],[430,740],[768,600],[1440,600],[390,360]]) {
  await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<640});await wait(220)
  await checkModalScroll(`Sign in ${width}x${height}`)
 }
 await click('Create account')
 for(const [width,height] of [[360,640],[390,700],[430,740],[768,600],[1440,600],[390,360]]) {
  await command('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<640});await wait(100)
  await checkModalScroll(`Registration ${width}x${height}`)
 }
 console.log('PASS sign-in and signup scroll with wheel; bottom links reachable on mobile, short desktop and keyboard-height viewport')
 for(const width of [360,390,768,1440]){
  await command('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:width<640})
  assert.equal(await evaluate(`document.documentElement.scrollWidth<=document.documentElement.clientWidth+1`),true)
  assert.equal(await evaluate(`document.querySelector('[role="dialog"]').contains(document.activeElement)`),true)
 }
 await fill('input[name="first_name"]','New');await fill('input[name="last_name"]','Customer');await fill('input[name="email"]','New@example.com');await fill('input[name="password"]','Password123!');await fill('input[name="confirmation"]','Different123!')
 await click('Create account');await until(`document.body.innerText.includes('passwords do not match')`);assert.equal(calls.length,0)
 await fill('input[name="confirmation"]','Password123!');mode='duplicate';await click('Create account');await until(`document.body.innerText.includes('already registered')`)
 mode='ok';await evaluate(`(()=>{const form=document.querySelector('form[aria-label="Create customer account"]');form.requestSubmit();form.requestSubmit()})()`)
 await until(`document.body.innerText.includes('Account created.')`);assert.equal(calls.filter(x=>x.path.endsWith('/register/customer')).length,2)
 assert.equal(calls[1].body.role,undefined)
 // Sign-in is explicit after registration, and uses the existing token callback.
 await fill('input[name="password"]','Password123!')
 await evaluate(`(()=>{const form=document.querySelector('form[aria-label="Password sign in"]');form.requestSubmit();form.requestSubmit()})()`)
 await until(`!document.querySelector('[role="dialog"]')`);assert.equal(calls.filter(x=>x.path.endsWith('/login')).length,1)
 assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),'fixture-account-token')
   await until(`location.pathname==='/membership/pause' && document.body.innerText.includes('Pause Membership')`)
 console.log('PASS registration mismatch/duplicate/success, duplicate-submit prevention, existing login callback, responsive form')
 await evaluate(`localStorage.clear()`);await visit('/auth/forgot-password','Enter your account email.')
 await fill('input[name="email"]','new@example.com');await click('Send reset link');await until(`document.body.innerText.includes('If an active account exists')`)
 emailAvailable=false;await visit('/auth/forgot-password','Password reset email is not available yet');assert.equal(await evaluate(`document.querySelector('main input')===null`),true)
 emailAvailable=true
 await visit('/auth/reset-password','This reset link is missing or invalid.')
 const token='fixture-reset-token-that-is-not-a-valid-secret'
 await visit('/auth/reset-password#token='+token,'Confirm new password')
 assert.equal(await evaluate('location.hash'),'')
 await fill('input[name="new_password"]','Replacement123!');await fill('input[name="confirmation"]','Replacement123!');mode='expired';await click('Reset password');await until(`document.body.innerText.includes('invalid or expired')`)
 mode='ok';await click('Reset password');await until(`document.body.innerText.includes('Password updated')`)
 assert.equal(calls.at(-1).body.token,token);assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),null)
 console.log('PASS forgot request, unconfigured email, invalid link, expired link, reset success, secret removed from URL')
 for(const role of ['GYM_OWNER','GYM_STAFF']){
  roles=[role];await evaluate(`localStorage.setItem('fitigo:access_token','fixture-owner-token')`)
  await visit('/owner/settings','Change password');await click('Change password')
  await fill('input[name="current_password"]','Password123!');await fill('input[name="new_password"]','Replacement123!');await fill('input[name="confirmation"]','Replacement123!')
  mode='wrong';await click('Change password');await until(`document.body.innerText.includes('current password is incorrect')`)
  mode='ok';await click('Change password');await until(`document.body.innerText.includes('Password updated. Sign in with your new password.')`)
  assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`),null)
 }
 assert.deepEqual(errors,[])
 console.log('PASS owner and staff change password, incorrect-current-password error, logout and new sign-in prompt')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await target.dispose()}