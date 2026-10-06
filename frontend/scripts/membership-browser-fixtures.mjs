// TEST ONLY: isolated network fixtures for UI behavior. Never bundled with production.
// Does not authenticate to or mutate the real backend; real API sign-off is separate.
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target = await isolatedBrowserTarget()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0; const pending = new Map(); const exceptions = []; const failures = []
function command(method, params = {}) { return new Promise((resolve,reject) => { const id=++sequence; const timer=setTimeout(()=>reject(new Error(`CDP timeout: ${method}`)),20000); pending.set(id,{resolve,reject,timer}); ws.send(JSON.stringify({id,method,params})) }) }
const now = new Date(); const year = now.getUTCFullYear(); const month = now.getUTCMonth()+1; const today = now.toISOString().slice(0,10)
const start = `${year}-${String(month).padStart(2,'0')}-01T00:00:00Z`
const end = new Date(Date.UTC(year,month,1)).toISOString()
let mode = 'ACTIVE'; let scope = 'MULTI_GYM'; let qrRequests = 0; let expireQuickly = false; let failure = null; let empty = false
let delayCalendar = false; let cart = []; let submittedCart = []; let payments = 0
let platformEmpty = true; let platformDelay = false; let platformOrder = null; let orderRequests = 0; let platformUnavailable = false
let walletMvp = false; let membershipPayments = 0; let singlePayments = 0
const platformPlans = Array.from({length:4},(_,index)=>({id:index+21,code:`fixture-${index}`,name:`Test platform plan ${index+1}`,membership_type:'MULTI_GYM',description:'Test-only platform plan',duration_value:index+1,duration_unit:'MONTH',base_price:'1600.00',final_price:index===1?'1280.00':index===2?'1450.00':'1600.00',discount_amount:index===1?'320.00':index===2?'150.00':'0.00',discount_percentage:index===1?'20.00':null,currency:'INR',offer:index===1||index===2?{id:index,kind:index===1?'PERCENTAGE':'FIXED',title:index===1?'Test seasonal offer':null,valid_until:new Date(Date.now()+3600000).toISOString()}:null,benefits:['Server-configured benefit'],badge:index===2?'Test badge':null,display_order:index,is_active:true,version:1,access_rule:{scope:'ELIGIBLE_PARTNER_GYMS',daily_access:1},pause_rule:null,purchase_available:false}))
const user = { id:1,first_name:'Test',last_name:'Member',email:'member-fixture@example.test',phone:null }
const memberships = [{ id:1,user_id:1,gym_id:1,plan_id:1,status:'ACTIVE',start_at:start,end_at:end,paid_amount:'1200.00',currency:'INR',payment_provider:'TEST',payment_status:'PAID' }]
const plan = { id:1,gym_id:1,name:'Test Monthly Plan',description:'Test-only membership',duration_days:30,price:'1200.00',currency:'INR',is_active:true }
const gym = { gym_id:1,gym_name:'Test Movement Studio',slug:'test',location:{locality:'Test District',city:'Test City',full_address:'Test Street'},ratings:{average_rating:null,review_count:0},images:[],opening_hours:{open_now:true,open_today:'06:00 – 22:00',weekly:[]},workout_options:[],amenities:[],description:'Test-only gym',important_information:[],rules:[],membership_access:{status:'INCLUDED',upgrade_required:false,day_pass_available:false},classes_nearby:[],related_gyms:[],reviews:[] }
function calendar(y,m) {
  const length = new Date(Date.UTC(y,m,0)).getUTCDate()
  const fixtureDays = Array.from({length},(_,index)=>index).filter(index=>`${y}-${String(m).padStart(2,'0')}-${String(index+1).padStart(2,'0')}`!==today)
  const days = Array.from({length},(_,index)=> {
    const date = `${y}-${String(m).padStart(2,'0')}-${String(index+1).padStart(2,'0')}`
    if(date===today) return {date,status:'TODAY',qr_available:mode==='ACTIVE',qr_status:mode==='ACTIVE'?'ACTIVE':mode==='USED'?'USED':mode==='PAUSED'?'PAUSED':'NO_ACCESS',gym_id:mode==='USED'?1:null,gym_name:mode==='USED'?gym.gym_name:null,checkin_time:mode==='USED'?'08:15:00':null}
    if(index===fixtureDays[0]) return {date,status:'VISITED',qr_available:false,qr_status:'USED',gym_id:1,gym_name:gym.gym_name,checkin_time:'07:30:00'}
    if(index===fixtureDays[1]) return {date,status:'NO_VISIT',qr_available:false,qr_status:'EXPIRED',gym_name:null,checkin_time:null}
    if(index===fixtureDays[2]) return {date,status:'PAUSED',qr_available:false,qr_status:'PAUSED',gym_name:null,checkin_time:null}
    return {date,status:'FUTURE',qr_available:false,qr_status:null,gym_name:null,checkin_time:null}
  })
  return {year:y,month:m,access_type:scope,gym:scope==='SINGLE_GYM'?{id:1,name:gym.gym_name}:null,days}
}
function fixture(url,method,postData) {
  const {pathname:path,searchParams:query}=new URL(url)
  if(path==='/api/v1/auth/session')return {user,roles:['CUSTOMER']}
  if(path.endsWith('/pay-wallet') && method==='POST') {
    const body=JSON.parse(postData);assert.deepEqual(body,{accepted_quote:'fixture-quote'});membershipPayments++
    Object.assign(memberships[0],{membership_type:'MULTI_GYM',gym_id:null,plan_id:null,terms_snapshot:platformOrder.plan,payment_provider:'WALLET'})
    return {...platformOrder,membership_id:1,payment_status:'PAID',payment_available:false,wallet_transaction_id:51}
  }
  if(path==='/api/v1/memberships/gyms/1/purchase' && method==='POST') {
    assert.deepEqual(JSON.parse(postData),{plan_id:1,accepted_quote:'fixture-single-quote'});singlePayments++
    Object.assign(memberships[0],{membership_type:'SINGLE_GYM',gym_id:1,plan_id:1,terms_snapshot:null,payment_provider:'WALLET'})
    return memberships[0]
  }
  if(path==='/api/v1/memberships/orders' && method==='POST') {
    const body=JSON.parse(postData);assert.deepEqual(Object.keys(body),['plan_id']);orderRequests++
    platformOrder={id:'11111111-2222-4333-8444-555555555555',plan:structuredClone(platformPlans.find(plan=>plan.id===body.plan_id)),status:'PAYMENT_DISABLED',payment_status:'NOT_STARTED',eligibility_status:'NOT_EVALUATED',created_at:new Date().toISOString(),payment_available:false,membership_id:null}
    return {...platformOrder,current_plan:platformOrder.plan,requires_review:false}
  }
  if(path==='/api/v1/cart/items/gym' && method==='POST') {
    const body=JSON.parse(postData);submittedCart.push(body)
    const item={...body,id:1,status:'ACTIVE',price_per_person:'425.00',total_price:(425*body.member_count).toFixed(2),currency:'INR',gym_name:gym.gym_name}
    cart=[item];return item
  }
  if(path==='/api/v1/cart/checkout/wallet' && method==='POST') {payments++;return {confirmed_items:cart,total_amount:cart[0].total_price,currency:'INR',wallet_balance_before:'5000.00',wallet_balance_after:'4150.00',wallet_transaction_id:1,booking_ids:[41]}}
  if(method!=='GET') throw new Error(`Unexpected mutation ${method} ${path}`)
  if(path==='/api/v1/memberships/plans') return {items:platformEmpty?[]:platformPlans,server_time:new Date().toISOString(),checkout_available:false,checkout_unavailable_reason:'PAYMENT_NOT_CONFIGURED'}
  if(path.startsWith('/api/v1/memberships/orders/')) {const current=platformUnavailable?null:platformPlans.find(plan=>plan.id===platformOrder.plan.id);return {...platformOrder,current_plan:current,requires_review:JSON.stringify(current)!==JSON.stringify(platformOrder.plan),payment_available:walletMvp,quote_token:'fixture-quote',wallet_balance:'5000.00',wallet_currency:'INR'}}
  if(path==='/api/v1/memberships/gyms/1/plans/1/wallet-quote') return {plan:{name:plan.name,final_price:plan.price,currency:'INR',duration_value:30,duration_unit:'DAY'},quote_token:'fixture-single-quote',payment_available:walletMvp,wallet_balance:'5000.00',wallet_currency:'INR',payment_mode:'WALLET_TEST_CREDIT'}
  if(path==='/api/v1/cart/items')return cart
  if(path==='/api/v1/wallet/balance')return {balance:'5000.00',currency:'INR'}
  if(path==='/api/v1/bookings/41')return {id:41,gym_id:1,slot_date:today,quantity:cart[0]?.member_count||2,total_price:cart[0]?.total_price||'850.00',currency:'INR',status:'CONFIRMED',notes:null,cancelled_at:null,payment:{status:'PAID',amount:cart[0]?.total_price||'850.00',currency:'INR',provider:'TEST'}}
  if(path==='/api/v1/profile/bookings')return []
  if(/^\/api\/v1\/gyms\/\d+\/booking-options$/.test(path))return {gym_id:Number(path.split('/')[4]),gym_name:gym.gym_name,membership_status:{status:'NO_ACTIVE_MEMBERSHIP',title:'Day visit',tone:'info'},available_access_types:[],workout_areas:[],gym_price_per_person:'425.00',has_classes:true}
  if(/^\/api\/v1\/gyms\/\d+\/operating-hours$/.test(path))return {gym_id:Number(path.split('/')[4]),date:query.get('date'),day_of_week:1,open_time:'06:00:00',close_time:'22:00:00',is_closed:false}
  if(/^\/api\/v1\/gyms\/\d+\/class-sessions$/.test(path))return []
  if(path==='/api/v1/users/me') return user
  if(path==='/api/v1/meta/gym-types' || path==='/api/v1/facilities') return []
  if(path==='/api/v1/memberships/me') return empty?[]:memberships
  if(path==='/api/v1/memberships/me/1/pause')return {membership_id:1,membership_status:memberships[0].status,pause_allowed:false,can_pause:false,max_pause_days:0,pause_days_used:0,pause_days_remaining:0,currently_paused:false,eligible_from:null,eligible_until:null,original_end_at:end,current_end_at:memberships[0].end_at,current_pause:null,history:[],reason_code:'PAUSE_NOT_ALLOWED',timezone:'UTC'}
  if(path==='/api/v1/profile/membership') return {membership_id:empty?null:1,plan_name:empty?null:plan.name,status:empty?null:memberships[0].status,start_date:start,end_date:end,membership_scope:scope,active_gyms:empty?[]:[{gym_id:1,gym_name:gym.gym_name,locality:'Test District',city:'Test City'}],membership_features:[]}
  if(path==='/api/v1/memberships/gyms/1/plans') return [plan]
  if(path==='/api/v1/gyms/1/details') return gym
  if(path==='/api/v1/gyms/2/details') return {...gym,gym_id:2,membership_access:{...gym.membership_access,status:'NO_ACTIVE_MEMBERSHIP'}}
  if(path==='/api/v1/customer/access-calendar') return calendar(Number(query.get('year')),Number(query.get('month')))
  if(path==='/api/v1/customer/access/today') {
    qrRequests++
    if(mode==='USED') return {status:'USED',gym_name:gym.gym_name,used_at:`${today}T08:15:00Z`}
    if(mode!=='ACTIVE') return {status:mode==='PAUSED'?'PAUSED':'NO_ACCESS'}
    return {status:'ACTIVE',access_type:scope,gym:scope==='SINGLE_GYM'?{id:1,name:gym.gym_name}:null,qr_token:'GYMACCESS:test-only-nonfunctional-browser-fixture',expires_at:new Date(Date.now()+(expireQuickly?1500:300000)).toISOString()}
  }
  if(path==='/api/v1/gyms/discover') {
    if(query.has('membership_access'))assert.equal(query.get('membership_access'),'INCLUDED')
    return {total_count:query.get('search')?0:1,page:Number(query.get('page')||1),page_size:12,has_more:false,gyms:query.get('search')?[]:[{gym_id:1,gym_name:gym.gym_name,primary_image:null,locality:'Test District',city:'Test City',review_count:0,facilities:[],is_featured:false,membership_access_status:'INCLUDED',is_open_now:true}]}
  }
  throw new Error(`Unexpected request ${path}`)
}
ws.onmessage=async event=>{
  const message=JSON.parse(event.data)
  if(message.id&&pending.has(message.id)){const item=pending.get(message.id);clearTimeout(item.timer);pending.delete(message.id);message.error?item.reject(new Error(message.error.message)):item.resolve(message.result)}
  if(message.method==='Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text)
  if(message.method==='Fetch.requestPaused'){
    const {requestId,request}=message.params
    if(request.url.includes('/customer/access-calendar'))calendarRequests++
    try{
      if(delayCalendar && request.url.includes('/customer/access-calendar'))await new Promise(resolve=>setTimeout(resolve,600))
      if(platformDelay && request.url.includes('/memberships/plans'))await new Promise(resolve=>setTimeout(resolve,800))
      if(request.method==='POST' && request.url.endsWith('/memberships/orders'))assert.ok(request.headers['Idempotency-Key'] || request.headers['idempotency-key'])
      if(failure&&request.url.includes(failure.path)) {
        if(failure.status===0) await command('Fetch.failRequest',{requestId,errorReason:'ConnectionFailed'})
        else await command('Fetch.fulfillRequest',{requestId,responseCode:failure.status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify({detail:failure.code?{code:failure.code,message:'SQL private detail'}:'SQL private detail'})).toString('base64')})
      } else await command('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(fixture(request.url,request.method,request.postData))).toString('base64')})
    }catch(error){failures.push(error.message);await command('Fetch.fulfillRequest',{requestId,responseCode:500,body:Buffer.from('{}').toString('base64')})}
  }
}
async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw new Error(result.exceptionDetails.text);return result.result.value}
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms))
let calendarRequests=0
async function until(expression){for(let i=0;i<150;i++){if(await evaluate(expression))return;await wait(120)}throw new Error(`Not ready ${expression}: ${await evaluate('document.body.innerText.slice(-900)')}`)}
async function visit(path,text){await command('Page.navigate',{url:'http://localhost:5173'+path});await until(`document.body.innerText.includes(${JSON.stringify(text)})`);await until(`!document.querySelector('[aria-label="Loading"]')`)}
async function width(value){await command('Emulation.setDeviceMetricsOverride',{width:value,height:950,deviceScaleFactor:1,mobile:value<640});await wait(80);const sizes=await evaluate('({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})');assert.ok(sizes.scroll<=sizes.client+1,`Overflow at ${value}: ${JSON.stringify(sizes)}`)}
async function click(text,selector='button'){await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`);await wait(100)}
async function shot(name){const image=await command('Page.captureScreenshot',{format:'png'});await writeFile(join(tmpdir(),name),Buffer.from(image.data,'base64'))}
async function fill(selector,value){await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}));})()`);await wait(60)}
try{
  await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*://localhost:5173/api/v1/*'}]})
  await visit('/membership','Welcome to FitiGo');await evaluate(`localStorage.setItem('fitigo:access_token','test-only-customer-token')`)
  await visit('/membership','My Membership');await until(`document.body.innerText.includes('Test Monthly Plan')`)
  assert.equal(qrRequests,0,'Opening membership must not mint QR')
  for(const value of [360,375,390,430,768,1024,1280,1440,1920])await width(value)
  await width(390);await shot('fitigo-membership-mobile.png');await width(1440);await shot('fitigo-membership-desktop.png')
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('.fg-bottom-nav a')).map(el=>el.textContent.trim()).join(',')`),'Home,Explore,Memberships,Profile')
  scope='SINGLE_GYM';await visit('/membership/1','This gym only');await width(360);await visit('/membership/1/details','Current expiry');scope='MULTI_GYM'
  await visit('/gyms','Visit This Gym');await width(360);await width(1440)
  await evaluate(`(()=>{const el=document.querySelector('.fm-search input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'no-match');el.dispatchEvent(new Event('input',{bubbles:true}));})()`)
  await until(`document.body.innerText.includes('No eligible gyms available nearby')`)
  await visit('/gyms/1/visit','Generate Visit QR');assert.equal(qrRequests,0,'Confirmation must not mint QR');await width(360)
  await click('Generate Visit QR','a');await until(`!!document.querySelector('.fm-qr-frame svg')`);assert.equal(qrRequests,1,'One server credential request despite StrictMode')
  for(const value of [360,375,390,430,768,1024,1280,1440])await width(value)
  await width(390);await shot('fitigo-membership-qr.png')
  mode='USED';await until(`document.body.innerText.includes('Check-in Successful!')`);assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`),false);assert.equal(qrRequests,1,'Polling must not mint replacement QR')
  await visit('/access/qr?gymId=1','You’ve used your access today.');assert.equal(qrRequests,1,'Already used cannot mint QR')
  mode='PAUSED';await visit('/membership','Gym access is unavailable during a pause');assert.equal(await evaluate(`!!document.querySelector('main a[href="/gyms"]')`),false)
  await visit('/access/qr?gymId=1','Gym access is unavailable during a pause');assert.equal(qrRequests,1)
  await visit('/membership/pause','Pause unavailable for this membership plan.');assert.equal(await evaluate(`document.querySelectorAll('main input[type="date"]').length`),0)
  mode='ACTIVE';await visit('/gyms/2/visit','Membership access isn’t available today');assert.equal(qrRequests,1)
  await visit('/profile/access','Membership Calendar');for(const value of [360,375,390,430,768,1024,1280,1440])await width(value)
  await width(390);await shot('fitigo-membership-calendar.png');assert.equal(qrRequests,1)
  await visit('/profile/visits','Visit History');await until(`document.querySelectorAll('.fm-history-list article').length===1`)
  assert.equal(await evaluate(`document.querySelector('.fm-history-list')?.innerText.includes('consumed')`),false)
  await click('All access activity');assert.equal(await evaluate(`document.querySelectorAll('.fm-history-list article').length`),3)
  expireQuickly=true;await visit('/access/qr?gymId=1','Show this QR to gym staff');await until(`document.body.innerText.includes('Refresh your access QR')`);assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`),false);expireQuickly=false
  failure={path:'/customer/access/today',status:403,code:'DAILY_ACCESS_ALREADY_CONSUMED'};await visit('/access/qr?gymId=1','Today’s Access Already Used');assert.equal(await evaluate(`document.body.innerText.includes('SQL')`),false);failure=null
  await visit('/access/qr?gymId=1','Show this QR to gym staff');await evaluate(`window.dispatchEvent(new Event('offline'))`);await until(`document.body.innerText.includes('Unable to connect')`);assert.equal(await evaluate(`!!document.querySelector('.fm-qr-frame')`),false)
  await click('Retry');await until(`!!document.querySelector('.fm-qr-frame')`)
  for(const status of [500,0]){failure={path:'/memberships/me',status};await visit('/membership',status===0?'Unable to connect':'Unable to load your membership information');failure=null;await click('Try again');await until(`document.body.innerText.includes('Test Monthly Plan')`)}
  empty=true;await visit('/membership','Your next chapter starts here')
  assert.equal(await evaluate(`document.querySelector('main h1').textContent`),'My Membership')
  assert.equal(await evaluate(`document.body.innerText.includes('Everything you need for your next workout.')`),true)
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('.fm-choice-card a')).map(el=>el.textContent.trim())`),['View Multi-Gym Plans','Explore Gyms'])
  assert.equal(await evaluate(`document.querySelectorAll('.fm-choice-card').length`),2)
  for(const value of [360,375,390,430,768,1024,1280,1440]) {
    await width(value)
    assert.equal(await evaluate(`getComputedStyle(document.querySelector('.fm-choice-grid')).gridTemplateColumns.split(' ').length`),value<768?1:2)
  }
  await width(1440);await shot('fitigo-no-membership-desktop.png');await width(390);await shot('fitigo-no-membership-mobile.png')
  await click('View Multi-Gym Plans','a');await until(`location.pathname==='/membership/multi-gym/plans' && document.body.innerText.includes("Multi-Gym plans aren't available right now.")`)
  await evaluate('history.back()');await until(`document.querySelectorAll('.fm-choice-card').length===2`)
  await click('Explore Gyms','a');await until(`location.pathname==='/explore' && document.body.innerText.includes('Test Movement Studio')`)
  await evaluate(`document.querySelector('a[href="/gyms/1"]').click()`);await until(`document.body.innerText.includes('View Membership Plans')`)
  await click('View Membership Plans','a');await until(`location.pathname==='/gyms/1/membership' && document.body.innerText.includes('Test Monthly Plan')`)
  empty=false;mode='NO_ACCESS'
  for(const status of ['EXPIRED','INACTIVE','CANCELLED','NONE']) {
    memberships[0].status=status;await visit('/membership','Your next chapter starts here')
    assert.equal(await evaluate(`!!document.querySelector('.fm-membership-history')`),true)
    assert.equal(await evaluate(`!!document.querySelector('.fm-current-access')`),false)
  }
  memberships[0].status='ACTIVE';mode='ACTIVE';await visit('/membership','Test Monthly Plan')
  assert.equal(await evaluate(`!!document.querySelector('.fm-membership-choices')`),false)
  memberships[0].status='EXPIRED';mode='NO_ACCESS';await visit('/membership/1','Your FitiGo membership expired on');assert.equal(await evaluate(`document.querySelector('main')?.innerText.includes('Plan today’s visit')`),false)
  memberships[0].status='ACTIVE';mode='ACTIVE';scope='SINGLE_GYM'
  await visit('/gyms/1','Book a Visit')
  assert.equal(await evaluate(`document.querySelector('main')?.innerText.includes('Generate Visit QR')`),false)
  assert.equal(await evaluate(`document.querySelector('main')?.innerText.includes('Book for Others')`),false)
  assert.equal(await evaluate(`document.querySelector('main a[href="/gyms/1/membership"]')?.textContent`),'View Membership Plans')
  for(const value of [360,375,390,430,768,1024,1280,1440])await width(value)
  delayCalendar=true;await click('Book a Visit');assert.equal(await evaluate('location.pathname'),'/gyms/1');await until(`document.body.innerText.includes('Checking your membership access')`)
  await until(`!!document.querySelector('dialog[open]')`);delayCalendar=false
  assert.equal(await evaluate('location.pathname'),'/gyms/1')
  assert.deepEqual(await evaluate(`Array.from(document.querySelectorAll('dialog button')).map(el=>el.textContent.trim())`),['Use My Membership','Book for Others'])
  assert.equal(await evaluate(`document.querySelector('dialog').contains(document.activeElement)`),true)
  await width(1440);await shot('fitigo-membership-choice-desktop.png')
  for(const value of [360,375,390,430,768,1024,1280,1440])await width(value)
  await width(390);await shot('fitigo-membership-choice-mobile.png')
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9})
  assert.equal(await evaluate(`document.querySelector('dialog').contains(document.activeElement)`),true)
  await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await until(`!document.querySelector('dialog[open]')`)
  assert.equal(await evaluate('location.pathname'),'/gyms/1')
  await click('Book a Visit');await until(`!!document.querySelector('dialog[open]')`)
  await evaluate(`document.querySelector('dialog').dispatchEvent(new MouseEvent('click',{bubbles:true}))`);await until(`!document.querySelector('dialog[open]')`)
  await click('Book a Visit');await until(`!!document.querySelector('dialog[open]')`)
  await click('Use My Membership','dialog button');await until(`location.pathname==='/my-access'`);await until(`document.body.innerText.includes('Generate Visit QR')`)
  assert.equal(await evaluate(`document.querySelector('main')?.innerText.includes('Book for Others')`),false)
  assert.equal(await evaluate(`!!document.querySelector('main a[href*="/book/"]')`),false)
  for(const value of [360,375,390,430,768,1024,1280,1440])await width(value)
  await width(390);await shot('fitigo-my-access.png')
  const beforeCompanionsQr=qrRequests
  await visit('/gyms/1','Book a Visit');await click('Book a Visit');await until(`!!document.querySelector('dialog[open]')`)
  await click('Book for Others','dialog button');await until(`location.pathname==='/gyms/1/book/schedule'`);assert.equal(await evaluate('location.search'),'?for=others');await until(`document.body.innerText.includes('Additional people')`);await until(`document.querySelectorAll('input[type="time"]').length===2`)
  await evaluate(`history.back()`);await until(`location.pathname==='/gyms/1'`);await until(`!document.querySelector('[aria-label="Loading"]')`)
  assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`),false)
  await click('Book a Visit');await until(`!!document.querySelector('dialog[open]')`);await click('Book for Others','dialog button');await until(`document.body.innerText.includes('Additional people')`);await until(`document.querySelectorAll('input[type="time"]').length===2`)
  assert.equal(await evaluate(`document.querySelector('input[type="date"]').readOnly`),true)
  assert.equal(await evaluate(`document.querySelector('input[type="date"]').value`),today)
  await evaluate(`document.querySelector('[aria-label="Add one member"]').click()`)
  await fill('input[type="time"]','09:00')
  await evaluate(`(()=>{const el=document.querySelectorAll('input[type="time"]')[1];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'10:00');el.dispatchEvent(new Event('input',{bubbles:true}));})()`)
  await wait(80);await width(360);await shot('fitigo-companion-booking.png')
  await click('Check availability & add to cart');await until(`location.pathname==='/cart'`);await until(`document.body.innerText.includes('Proceed to checkout')`)
  assert.equal(submittedCart.length,1);assert.equal(submittedCart[0].member_count,2);assert.equal(submittedCart[0].booking_date,today)
  assert.equal(qrRequests,beforeCompanionsQr);assert.equal(cart[0].total_price,'850.00')
  await click('Proceed to checkout','a');await until(`document.body.innerText.includes('using wallet')`)
  await evaluate(`Array.from(document.querySelectorAll('button')).find(el=>el.textContent.includes('using wallet')).click()`);await until(`!!document.querySelector('dialog[open]')`)
  await click('Confirm payment');await until(`location.pathname==='/booking/41/success'`);await until(`document.body.innerText.includes('Booking confirmed!')`);assert.equal(payments,1)
  await visit('/gyms/1/book/schedule?for=others','Additional people');await fill('input[type="time"]','09:00');await evaluate(`(()=>{const el=document.querySelectorAll('input[type="time"]')[1];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'10:00');el.dispatchEvent(new Event('input',{bubbles:true}));})()`);await wait(80)
  mode='USED';await click('Check availability & add to cart');await until(`location.pathname==='/gyms/1/book/access'`);assert.equal(submittedCart.length,1)
  await visit('/gyms/1','Book a Visit');await click('Book a Visit');await until(`location.pathname==='/gyms/1/book/access'`);assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`),false)
  await visit('/my-access?gymId=1','You’ve used your access today.')
  assert.equal(await evaluate(`document.querySelector('main')?.innerText.includes('Book for Others')`),false)
  assert.equal(await evaluate(`document.querySelector('main')?.innerText.includes('Generate Visit QR')`),false)
  mode='PAUSED';await visit('/gyms/1','Book a Visit');await click('Book a Visit');await until(`location.pathname==='/gyms/1/book/access'`)
  mode='NO_ACCESS';await visit('/gyms/1','Book a Visit');await click('Book a Visit');await until(`location.pathname==='/gyms/1/book/access'`)
  // Explicit no-membership must not request the membership calendar at all.
  // Arm a calendar failure so the previous Promise.all implementation fails this regression.
  mode='NO_ACCESS';empty=true;gym.membership_access.status='NO_ACTIVE_MEMBERSHIP'
  await visit('/gyms/1','Book a Visit');const noMembershipCalendars=calendarRequests
  failure={path:'/customer/access-calendar',status:404}
  await click('Book a Visit');await until(`location.pathname==='/gyms/1/book/access'`);await until(`document.body.innerText.includes('How do you want to work out?')`)
  assert.equal(calendarRequests,noMembershipCalendars);assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`),false)
  assert.equal(await evaluate(`document.body.innerText.includes('No membership found') || document.body.innerText.includes('Unable to check your membership access')`),false)
  failure=null;empty=false;gym.membership_access.status='INCLUDED';mode='ACTIVE'
  await visit('/gyms/2','Book a Visit');const incompatibleCalendars=calendarRequests
  await click('Book a Visit');await until(`location.pathname==='/gyms/2/book/access'`);await until(`document.body.innerText.includes('How do you want to work out?')`)
  assert.equal(calendarRequests,incompatibleCalendars)
  await click('Continue');await until(`document.body.innerText.includes('You and your workout crew')`)
  await fill('input[type="time"]','09:00');await evaluate(`(()=>{const el=document.querySelectorAll('input[type="time"]')[1];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'10:00');el.dispatchEvent(new Event('input',{bubbles:true}));})()`);await wait(80)
  await click('Check availability & add to cart');await until(`location.pathname==='/cart'`);assert.equal(submittedCart.length,2);assert.equal(submittedCart[1].gym_id,2);assert.equal(submittedCart[1].member_count,1)
  scope='MULTI_GYM';await visit('/gyms/1','Book a Visit');failure={path:'/customer/access-calendar',status:500};await click('Book a Visit');await until(`document.body.innerText.includes('Unable to check your membership access.')`);assert.equal(await evaluate('location.pathname'),'/gyms/1')
  failure=null;await click('Try Again');await until(`!!document.querySelector('dialog[open]')`);assert.equal(await evaluate('location.pathname'),'/gyms/1')
  await click('Use My Membership','dialog button');await until(`location.pathname==='/my-access'`);await until(`document.body.innerText.includes('FitiGo Multi-Gym')`)
  mode='USED';await visit('/gyms/1','Book a Visit');await click('Book a Visit');await until(`location.pathname==='/gyms/1/book/access'`);assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`),false);mode='ACTIVE'
  for(const path of ['/gyms/1/details','/customer/access-calendar'])for(const status of [0,404,500]){
    await visit('/gyms/1','Book a Visit');failure={path,status}
    await click('Book a Visit');await until(`document.body.innerText.includes('Unable to check your membership access.')`)
    assert.equal(await evaluate('location.pathname'),'/gyms/1');assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`),false)
    failure=null;await click('Try Again');await until(`!!document.querySelector('dialog[open]')`)
  }
  console.log('PASS no-membership skips calendar and opens normal booking; single/multi available and used; ineligible gym; network/404/500 failures require retry')
  await visit('/gyms/1/membership','Choose your membership');await width(360)
  await visit('/gyms/1/visit?entry=book','You have an active membership');await until(`!!document.querySelector('dialog[open]')`)
  assert.equal(await evaluate('location.pathname'),'/gyms/1/visit')
  await click('Use My Membership','dialog button');await until(`location.pathname==='/my-access'`)
  console.log('PASS TEST FIXTURES: exactly-two-button popup, available access waits for choice, keyboard/Escape, direct companion routing, used access goes directly to paid booking, personal-only My Access, two companions excluding self, unchanged checkout/payment confirmation, stale eligibility guard and membership plans')
  platformEmpty=false;platformDelay=true
  await command('Page.navigate',{url:'http://localhost:5173/membership/multi-gym/plans'})
  await until(`!!document.querySelector('.fm-plan-loading [aria-label="Loading"]')`)
  await until(`document.querySelectorAll('.fm-plan-card').length===4`);platformDelay=false
  assert.equal(await evaluate(`document.querySelectorAll('.fm-plan-card del').length`),2)
  assert.equal(await evaluate(`document.body.innerText.includes('20% OFF') && document.body.innerText.includes('Save ₹150')`),true)
  assert.equal(await evaluate(`document.querySelectorAll('.fm-plan-card')[0].querySelector('del')===null`),true)
  for(const value of [360,375,390,430,768,1024,1280,1440])await width(value)
  await width(1440);await shot('fitigo-platform-plans-desktop.png');await width(390);await shot('fitigo-platform-plans-mobile.png')
  await evaluate(`(()=>{const b=document.querySelectorAll('.fm-plan-card button')[1];b.click();b.click()})()`)
  await until(`location.pathname==='/membership/checkout' && document.body.innerText.includes('Wallet payment unavailable')`)
  assert.equal(orderRequests,1)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Wallet payment unavailable').disabled`),true)
  for(const value of [360,390,768,1440])await width(value)
  platformPlans[1].final_price='1200.00';platformPlans[1].version++
  await click('Refresh current price and balance');await until(`document.body.innerText.includes('This plan has changed')`)
  assert.equal(await evaluate(`document.querySelector('.fm-plan-price').textContent.includes('1,200')`),true)
  platformUnavailable=true;await click('Refresh current price and balance');await until(`document.body.innerText.includes('This plan is no longer available')`);platformUnavailable=false
  for(const status of [500,0]){failure={path:'/memberships/plans',status};await visit('/membership/multi-gym/plans',status===0?'Unable to connect':'Unable to load membership plans.');failure=null;await click('Try Again');await until(`document.querySelectorAll('.fm-plan-card').length===4`)}
  // Simulate the server's offer boundary: the client refreshes, never recomputes a discount.
  platformPlans[1].offer.valid_until=new Date(Date.now()+1800).toISOString()
  await visit('/membership/multi-gym/plans','Test seasonal offer')
  platformPlans[1].offer=null;platformPlans[1].final_price='1600.00';platformPlans[1].discount_percentage=null;platformPlans[1].discount_amount='0.00'
  await until(`!document.body.innerText.includes('Test seasonal offer') && document.querySelectorAll('.fm-plan-card del').length===1`)
  console.log('PASS TEST FIXTURES: backend plan ordering/prices, no/percentage/fixed offers, expiry refresh, 8 widths, loading/empty/network/server errors, ID-only duplicate-safe unpaid order review, refreshed price, withdrawn plan and disabled payment')
  walletMvp=true;scope='MULTI_GYM';mode='ACTIVE'
  await visit('/membership/checkout?orderId='+platformOrder.id,'Pay with Wallet')
  assert.equal(await evaluate(`document.body.innerText.includes('Test credits only')`),true)
  for(const value of [360,390,430,768,1024,1440])await width(value)
  await width(390);await shot('fitigo-wallet-membership-checkout.png')
  failure={path:'/pay-wallet',status:409,code:'INSUFFICIENT_WALLET_BALANCE'}
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.startsWith('Pay with Wallet')).click()`)
  await click('Confirm Wallet Payment');await until(`document.body.innerText.includes('does not have enough test credits')`)
  assert.equal(membershipPayments,0);failure=null;await click('Refresh checkout');await until(`!document.querySelector('dialog[open]') && document.body.innerText.includes('Pay with Wallet')`)
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.startsWith('Pay with Wallet')).click()`)
  await evaluate(`(()=>{const b=Array.from(document.querySelectorAll('dialog button')).find(b=>b.textContent==='Confirm Wallet Payment');b.click();b.click()})()`)
  await until(`location.pathname==='/membership/success' && document.body.innerText.includes('Your membership is active')`)
  assert.equal(membershipPayments,1)
  await visit('/membership/1/details','Wallet · Test credits')
  scope='SINGLE_GYM';await visit('/membership/checkout?gymId=1&planId=1','Pay with Wallet')
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.startsWith('Pay with Wallet')).click()`)
  await click('Confirm Wallet Payment');await until(`location.pathname==='/membership/success' && document.body.innerText.includes('Your membership is active')`)
  assert.equal(singlePayments,1)
  console.log('PASS TEST FIXTURES: wallet membership test-credit notices, insufficient balance, refresh/retry, duplicate-safe Multi-Gym payment, real-state success navigation, Multi-Gym detail without null gym calls and Single-Gym wallet checkout.')
  assert.deepEqual(exceptions,[]);assert.deepEqual(failures,[])
  console.log('PASS TEST FIXTURES: membership single/multi/details, 9 widths, navigation, server-filtered gyms, debounce, confirm, QR issuance, backend-reported check-in, already-used/paused/ineligible/expired states, QR expiry, calendar/history distinction, safe errors and retries. No real backend mutations.')
}finally{
  await evaluate(`localStorage.removeItem('fitigo:access_token');localStorage.removeItem('fitigo:refresh_token')`).catch(()=>{})
  await command('Fetch.disable');ws.close();await target.dispose()
}