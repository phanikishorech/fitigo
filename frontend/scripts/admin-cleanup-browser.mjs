// Mock every API; never touches actual customer records or financial settings.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject) => { ws.onopen=resolve;ws.onerror=reject })
let sequence=0, partial=false, walletReview=false;const pending=new Map(),errors=[],calls=[]
const origin=process.env.FITIGO_TEST_ORIGIN||'http://localhost:5173'
const category={sales_count:1,sales_value:'500.00',gateway_funded_value:'500.00',wallet_funded_value:'0.00',active:1,expired:0}
function fixture(url,method) {
  calls.push(url.pathname+url.search);assert.equal(method,'GET')
  if(url.pathname.endsWith('/auth/session'))return {user:{id:5,first_name:'Business',last_name:'Admin',email:'admin@example.test'},roles:['ADMIN']}
  if(url.pathname.endsWith('/notifications/inbox'))return {items:[],total:0,unread_count:0}
  if(url.pathname.endsWith('/notifications/me'))return []
  if(url.pathname.endsWith('/cart/summary'))return {count:0,total:'0.00',currency:'INR'}
  if(url.pathname.endsWith('/business/summary'))return {date_from:url.searchParams.get('date_from'),date_to:url.searchParams.get('date_to'),mode:'test',options:[{id:1,name:'Fixture Gym'}],
    overall:{visits:6,bookings:8,users:20,gyms:3,active_memberships:2},visits:{individual:3,single_gym:2,multi_gym:1,completed:6,upcoming:2,no_shows:1,cancelled:2},
    collections:{categories:{individual:partial?null:'300.00',single_gym:partial?null:'500.00',multi_gym:partial?null:'1000.00'},total:partial?null:'1800.00',known_dated_total:'1800.00',known_dated_categories:{individual:'300.00',single_gym:'500.00',multi_gym:'1000.00'},exclusion_reasons:partial?{PAYMENT_DATE_SCHEMA_MISSING:14}:{},undated_purchases:partial?14:0,unattributed_purchases:0,gym_gross_share:null,fitigo_commission:null,complete:!partial},
    wallet:{applicable:!url.searchParams.has('gym_id'),outstanding:walletReview||url.searchParams.has('gym_id')?null:'200.00',reason:walletReview?'1 wallet account(s) have mismatched balances.':url.searchParams.has('gym_id')?'Wallet liability is platform-wide.':null,credits:'300.00',spending:'100.00',cancellation_credits:'50.00'},bookings:{total:8,cancelled:2,no_show:1,cancellation_rate:25,no_show_rate:25},
    memberships:{categories:{SINGLE_GYM:category,MULTI_GYM:category}},customers:{most_active:[{user_id:1,visits:6}]},gyms:[{id:1,name:'Fixture Gym',status:'APPROVED',visits:6,attended_value:'300.00',single_membership_sales_value:'500.00'}],
    series:[{date:url.searchParams.get('date_from'),individual:3,single_gym:2,multi_gym:1,individual_collections:'300.00',single_gym_collections:'500.00',multi_gym_collections:'1000.00'}],
    definitions:{collections:'Purchases once, not included visits.',earnings:'Recorded shares only. Multi-Gym collections are not FitiGo earnings.',rates:'Cancelled / scheduled bookings.',inventory:'Current platform inventory.'}}
  if(url.pathname.endsWith('/business/memberships'))return {total:1,items:[{id:1,customer_id:1,customer_name:'Fixture Customer',email:'customer@example.test',gym_id:null,gym_name:null,kind:'MULTI_GYM',status:'ACTIVE',payment_status:'PAID',purchase_amount:'1000.00',mode:'test',purchased_at:'2026-11-01T10:00:00Z',valid_from:'2026-11-01T10:00:00Z',valid_until:'2026-12-01T10:00:00Z'}]}
  if(url.pathname.endsWith('/admin/gyms'))return [{id:1,name:'Fixture Gym',owner_user_id:2,city:'Pune',status:'APPROVED',is_active:true,created_at:'2026-11-01T10:00:00Z'}]
  if(url.pathname.endsWith('/admin/users'))return [{id:1,first_name:'Fixture',last_name:'Customer',email:'customer@example.test',phone:null,status:'ACTIVE',created_at:'2026-11-01T10:00:00Z',roles:['CUSTOMER']}]
  if(url.pathname.endsWith('/admin/bookings'))return []
  if(url.pathname.endsWith('/financial-settings/gyms'))return {items:[{id:1,name:'Fixture Gym'}],total:1}
  throw Error('Unexpected API '+url.pathname)
}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(Error(method)),20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value}
async function until(expression){for(let n=0;n<120;n++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100))}throw Error(expression+': '+await evaluate('document.body?.innerText')+' '+errors)}
ws.onmessage=async event=>{const m=JSON.parse(event.data),item=pending.get(m.id);if(item){clearTimeout(item.timer);pending.delete(m.id);m.error?item.reject(Error(m.error.message)):item.resolve(m.result)}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);if(m.method!=='Fetch.requestPaused')return;const {requestId,request}=m.params;try{const data=fixture(new URL(request.url),request.method);await command('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(data)).toString('base64')})}catch(error){errors.push(error.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'})}}
try {
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await command('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('fitigo:access_token','mock-admin-cleanup');window.exports=[];URL.createObjectURL=b=>{window.exports.push(b);return 'blob:fixture'};URL.revokeObjectURL=()=>{};HTMLAnchorElement.prototype.click=function(){if(!this.download)HTMLElement.prototype.click.call(this)}"})
 await command('Page.navigate',{url:origin+'/admin'});await until("document.body.innerText.includes('Verified visits over time')")
 const labels=await evaluate("Array.from(document.querySelectorAll('.ad-sidebar nav[aria-label=\"Admin navigation\"] a')).map(a=>a.textContent)")
 assert.deepEqual(labels,['Dashboard','Gyms','Users','Bookings','Memberships','Reports','Commission Settings'])
 for(const forbidden of ['Financial Reconciliation','Processing blockers','Request owner payout','Runtime settings'])assert.equal(await evaluate(`document.body.innerText.includes(${JSON.stringify(forbidden)})`),false)
 await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Last 7 days').click()")
 await until("document.body.innerText.includes('Verified visits over time')")
 assert.ok(calls.some(path=>path.includes('/business/summary?')))
 for(const width of [360,768,1440]){await command('Emulation.setDeviceMetricsOverride',{width,height:1100,deviceScaleFactor:1,mobile:width<640});assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),true,`dashboard width ${width}`)}
 for(const [path,text] of [['gyms','Fixture Gym'],['users','Fixture Customer'],['bookings','No bookings found.'],['memberships','Fixture Customer'],['reports','Visit report'],['commission-settings','Select a gym to view its settings']]){
   await command('Page.navigate',{url:origin+'/admin/'+path});await until(`document.body.innerText.includes(${JSON.stringify(text)})`)
   assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),true,path)
 }
 await command('Page.navigate',{url:origin+'/admin/reports'});await until("document.body.innerText.includes('Export CSV')")
  const reportHeaders={visits:'Date IST',revenue:'Date IST',gyms:'Gym',memberships:'Membership type',bookings:'Bookings',customers:'Customer ID',wallet:'Unused wallet now'}
  for(const [index,[value,header]] of Object.entries(reportHeaders).entries()) {
    await evaluate(`(()=>{const el=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.startsWith('Report')).querySelector('select');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}))})()`)
    await until(`document.querySelector('.ad-table th')?.textContent===${JSON.stringify(header)}`)
    await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='Export CSV').click()")
    assert.equal(await evaluate('window.exports.length'),index+1)
    const csv=await evaluate('window.exports.at(-1).text()')
    assert.ok(csv.startsWith(`"${header}"`)||csv.startsWith(`\uFEFF"${header}"`))
    assert.ok(csv.includes('"Environment","From","To"'))
    assert.ok(csv.includes('"test"'))
    assert.ok(!csv.includes('undefined')&&!csv.includes('[object Object]'))
    if(value==='revenue')assert.ok(csv.includes('"300.00","500.00","1000.00"'))
    if(value==='wallet')assert.ok(csv.includes('"200.00","300.00","100.00","50.00"'))
  }
  partial=true
  await command('Page.navigate',{url:origin+'/admin?gym_id=1&mode=test'})
  await until("document.body.innerText.includes('Verified collections — partial subtotal')")
  assert.equal(await evaluate("Array.from(document.querySelectorAll('.ad-metric')).find(c=>c.textContent.startsWith('Revenue collected')).querySelector('strong').textContent"),'Not available yet')
  await evaluate("Array.from(document.querySelectorAll('summary')).find(s=>s.textContent==='Why collections are unavailable').click()")
  await until("document.body.innerText.includes('14 purchase(s): Confirmed provider payment dates')")
  await evaluate("Array.from(document.querySelectorAll('summary')).find(s=>s.textContent==='Wallet activity').click()")
  await until("document.body.innerText.includes('Wallet liability is platform-wide.')")
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='View platform wallet balance with All gyms').click()")
  await until("Array.from(document.querySelectorAll('.ad-metric')).find(c=>c.textContent.startsWith('Unused customer wallet balance'))?.querySelector('strong').textContent.includes('200.00')")
  assert.ok(calls.filter(p=>p.includes('/business/summary')).at(-1).includes('mode=test'))
  assert.ok(!calls.filter(p=>p.includes('/business/summary')).at(-1).includes('gym_id'))
  walletReview=true
  await command('Page.reload')
  await until("document.body.innerText.includes('Wallet activity')")
  await evaluate("Array.from(document.querySelectorAll('summary')).find(s=>s.textContent==='Wallet activity').click()")
  await until("document.body.innerText.includes('1 wallet account(s) have mismatched balances.')")
 await command('Page.navigate',{url:origin+'/admin/financial-reconciliation'});await until("document.body.innerText.includes('Page not found')")
 assert.ok(!calls.some(path=>path.includes('/financial-reconciliation')||path.includes('/marketplace/payouts')))
 assert.deepEqual(errors,[])
 console.log('PASS seven modules/default landing/date filter/responsive dashboard/CSV export/removed technical route; API calls mocked, zero mutations.')
} finally {ws.close();await target.dispose()}