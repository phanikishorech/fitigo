// TEST ONLY: isolated browser fixtures, never changes live plans or accounts.
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
const targets = await (await fetch('http://localhost:9231/json')).json()
const ws = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0
const pending = new Map(), failures = [], exceptions = [], writes = []
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; const timer = setTimeout(() => reject(new Error(`Timeout: ${method}`)), 20000); pending.set(id, {resolve, reject, timer}); ws.send(JSON.stringify({id, method, params})) }) }
const user = {id:1,first_name:'Test',last_name:'Admin',email:'plan-admin@example.test',phone:null}
let plans = [{id:21,code:'test-plan',name:'Test Multi-Gym Plan',membership_type:'MULTI_GYM',description:'Test configuration',duration_value:1,duration_unit:'MONTH',base_price:'1200.00',final_price:'1200.00',discount_amount:'0.00',discount_percentage:null,currency:'INR',offer:null,benefits:['Test benefit'],badge:'Test badge',display_order:10,is_active:true,version:1,access_rule:{scope:'ELIGIBLE_PARTNER_GYMS',daily_access:1},pause_rule:null,purchase_available:false}]
let config = null, failure = null, delay = false, roles = ['ADMIN']
function fixture(request) {
  const {pathname:path} = new URL(request.url), method = request.method
  if (path === '/api/v1/users/me') return user
  if (path === '/api/v1/users/me/roles') return roles
  if (path === '/api/v1/admin/ping') return {status:'ok',user_id:1}
  if (path === '/api/v1/admin/membership-plans' && method === 'GET') return {items:plans,server_time:new Date().toISOString(),checkout_available:false,checkout_unavailable_reason:'PAYMENT_NOT_CONFIGURED'}
  if (path === '/api/v1/admin/membership-plans' && method === 'POST') {
    const body = JSON.parse(request.postData); writes.push({path,body})
    assert.equal(body.is_active,false)
    const plan = {...plans[0],...body,id:22,version:1,final_price:body.base_price}
    plans.push(plan); return plan
  }
  const match = path.match(/^\/api\/v1\/admin\/membership-plans\/(\d+)(\/offer)?$/)
  if (match) {
    const plan = plans.find(plan => plan.id === Number(match[1]))
    if (method === 'GET') return {plan,offer_configuration:config,server_time:new Date().toISOString()}
    assert.equal(method,'PUT')
    const body = JSON.parse(request.postData); writes.push({path,body})
    assert.equal(body.expected_version,plan.version)
    assert.equal('final_price' in body,false)
    assert.equal('purchase_available' in body,false)
    const {expected_version,...values} = body
    if (match[2]) { config = {id:1,...values,state:values.is_active?'SCHEDULED':'DISABLED'}; plan.offer = null }
    else Object.assign(plan,values,{final_price:values.base_price})
    plan.version++
    return plan
  }
  throw new Error(`Unexpected request ${method} ${path}`)
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) { const p=pending.get(message.id); clearTimeout(p.timer);pending.delete(message.id);message.error?p.reject(new Error(message.error.message)):p.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const {requestId,request} = message.params
    try {
      if (delay && request.url.includes('/admin/membership-plans')) await new Promise(resolve => setTimeout(resolve,600))
      if (failure && request.url.includes(failure.path) && (!failure.method || request.method === failure.method)) {
        if (failure.status === 0) await command('Fetch.failRequest',{requestId,errorReason:'ConnectionFailed'})
        else await command('Fetch.fulfillRequest',{requestId,responseCode:failure.status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify({detail:{code:failure.code,message:'SQL private diagnostics'}})).toString('base64')})
      } else {
        const body = fixture(request)
        await command('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
      }
    } catch(error) {
      // Aborted StrictMode/navigation requests no longer have an interception ID.
      if (!/Invalid InterceptionId/.test(error.message)) failures.push(error.message)
      await command('Fetch.fulfillRequest',{requestId,responseCode:500,body:Buffer.from('{}').toString('base64')}).catch(()=>{})
    }
  }
}
async function evaluate(expression) { const r=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.text);return r.result.value }
const wait = ms => new Promise(resolve => setTimeout(resolve,ms))
async function until(expression) { for(let i=0;i<150;i++){if(await evaluate(expression))return;await wait(100)}throw new Error(`Timeout ${expression}: ${await evaluate('document.body.innerText.slice(-1300)')}`) }
async function visit(path,text) { await command('Page.navigate',{url:'http://localhost:5173'+path});await until(`document.body.innerText.includes(${JSON.stringify(text)})`);await until(`!document.querySelector('[aria-label="Loading"]')`) }
async function click(text,selector='button') { await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`);await wait(80) }
async function fill(name,value,tag='input') {
  const proto = tag==='textarea'?'HTMLTextAreaElement':tag==='select'?'HTMLSelectElement':'HTMLInputElement'
  await evaluate(`(()=>{const el=document.querySelector('${tag}[name="${name}"]');Object.getOwnPropertyDescriptor(${proto}.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('${tag==='select'?'change':'input'}',{bubbles:true}));})()`); await wait(50)
}
async function width(value) { await command('Emulation.setDeviceMetricsOverride',{width:value,height:950,deviceScaleFactor:1,mobile:value<640});await wait(100);assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),true,`Overflow ${value}`) }
async function shot(name) { const image=await command('Page.captureScreenshot',{format:'png'});await writeFile(join(tmpdir(),name),Buffer.from(image.data,'base64')) }

try {
  await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*://localhost:5173/api/v1/*'}]})
  await visit('/admin/login','Welcome back');await evaluate(`localStorage.setItem('fitigo:access_token','test-only-admin')`)
  delay=true;await command('Page.navigate',{url:'http://localhost:5173/admin/membership-plans'});await until(`!!document.querySelector('[aria-label="Loading"]')`);await until(`document.body.innerText.includes('Test Multi-Gym Plan')`);delay=false
  assert.equal(await evaluate(`!!document.querySelector('nav a[href="/admin/membership-plans"][aria-current="page"]')`),true)
  for(const w of [360,390,430,768,1024,1280,1440,1920])await width(w)
  await width(1440);await shot('fitigo-admin-membership-plans.png')
  await click('Edit Plan','main a');await until(`!!document.querySelector('input[name="base_price"]')`)
  await fill('base_price','1450.00');await click('Review Changes');await until(`!!document.querySelector('dialog[open]')`)
  assert.equal(await evaluate(`document.querySelector('dialog').contains(document.activeElement)`),true)
  await evaluate(`(()=>{const b=Array.from(document.querySelectorAll('dialog button')).find(b=>b.textContent==='Confirm Save');b.click();b.click()})()`)
  await until(`location.pathname==='/admin/membership-plans' && document.body.innerText.includes('1,450')`)
  assert.equal(writes.length,1);assert.deepEqual(writes[0].body.benefits,['Test benefit']);assert.equal(writes[0].body.badge,'Test badge')
  await click('Manage Offer','main a');await until(`document.body.innerText.includes('Add an offer')`)
  await fill('value','15');await fill('title','Future promotion');await fill('starts_at','2030-10-01T00:00:00');await fill('ends_at','2030-10-20T00:00:00')
  await evaluate(`document.querySelector('input[name="is_active"]').click()`)
  for(const w of [360,390,768,1024,1440])await width(w)
  await width(390);await shot('fitigo-admin-offer-mobile.png')
  await click('Review Offer');await click('Confirm Save','dialog button');await until(`document.body.innerText.includes('Scheduled')`)
  assert.equal(config.starts_at,'2030-10-01T00:00:00.000Z');assert.equal(config.value,'15')
  await click('Disable Offer');await click('Confirm Save','dialog button');await until(`document.body.innerText.includes('Disabled')`)
  assert.equal(config.is_active,false);assert.equal(await evaluate(`document.querySelector('input[name="title"]').value`),'Future promotion')
  await visit('/admin/membership-plans/21','Edit Membership Plan');await fill('base_price','1700.00')
  failure={path:'/admin/membership-plans/21',method:'PUT',status:409,code:'PLAN_VERSION_CHANGED'}
  await click('Review Changes');await click('Confirm Save','dialog button');await until(`document.body.innerText.includes('Another administrator changed this plan')`)
  assert.equal(await evaluate(`document.body.innerText.includes('SQL private')`),false)
  await click('Back to editor','dialog button');failure=null;await click('Reload latest version');await click('Discard and reload','dialog button');await until(`document.querySelector('input[name="base_price"]')?.value==='1450.00'`)
  await visit('/admin/membership-plans/new','Create Membership Plan');await fill('name','New test plan');await fill('code','new-test-plan');await fill('base_price','700.00')
  await click('Review New Plan');await click('Confirm Save','dialog button');await until(`location.pathname==='/admin/membership-plans' && document.body.innerText.includes('New test plan')`)
  assert.equal(plans.length,2)
  const saved=plans;plans=[];await visit('/admin/membership-plans','No Multi-Gym plans yet');plans=saved
  for(const status of [500,0]) { failure={path:'/admin/membership-plans',status};await visit('/admin/membership-plans',status===0?'Unable to connect':'Unable to load this view');failure=null;await click('Try again');await until(`document.body.innerText.includes('Test Multi-Gym Plan')`) }
  roles=['CUSTOMER'];await visit('/admin/membership-plans','Access denied');assert.equal(await evaluate('location.pathname'),'/admin/access-denied')
  assert.deepEqual(failures,[]);assert.deepEqual(exceptions,[])
  console.log('PASS admin plans browser fixtures: navigation, loading/empty/retry, price edit, create inactive plan, scheduled/disabled offers, version conflict reload, duplicate prevention, role gate, accessible confirmation and 8 responsive widths. No live data changed.')
} finally {
  await evaluate(`localStorage.removeItem('fitigo:access_token')`).catch(()=>{})
  await command('Fetch.disable');ws.close()
}