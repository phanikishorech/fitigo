// Every API request is intercepted; no working account/data mutations.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin=process.env.FITIGO_TEST_ORIGIN||'http://127.0.0.1:5195'
const target=await isolatedBrowserTarget(),ws=new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
let seq=0,role='GYM_OWNER',cancelled=false,failProfile=true
const pending=new Map(),errors=[]
const user={id:1,first_name:'Fixture',last_name:'Owner',email:'owner@example.com',phone:null}
const booking={id:9,gym_id:1,gym_slot_id:1,slot_date:'2027-01-01',quantity:1,total_price:'100',currency:'INR',status:'CONFIRMED',created_at:'2026-11-01T00:00:00Z',attendance_status:null,attendance_marked_at:null,customer:{id:2,first_name:'Member',last_name:'Fixture'},slot:{id:1,name:'Visit',start_time:'14:00',end_time:'15:00'},payment:{status:'PAID'},allowed_actions:['CANCEL'],action_unavailable_reasons:{MARK_ATTENDED:'Use QR check-in.',MARK_NO_SHOW:'Admission window is open.'}}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,80))}throw Error(await evaluate('document.body.innerText'))}
async function click(text,selector='button'){await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`)}
ws.onmessage=async event=>{
 const m=JSON.parse(event.data),p=pending.get(m.id)
 if(p){pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
 if(m.method!=='Fetch.requestPaused')return
 const {requestId,request}=m.params,path=new URL(request.url).pathname
 try{
  let body,status=200
  if(path.endsWith('/auth/session'))body={user,roles:[role]}
  else if(path.endsWith('/gym-owner/gyms'))body=[{id:1,name:'Fixture gym',status:'APPROVED',is_active:true}]
  else if(path.endsWith('/gym-owner/bookings/9'))body=booking
  else if(path.endsWith('/gym-owner/bookings/9/cancel')){cancelled=true;booking.status='CANCELLED';booking.allowed_actions=[];body=booking}
  else if(path.endsWith('/gyms/1/members'))body={items:[{id:2,name:'Member Fixture',membership_status:'ACTIVE'}],total:1}
  else if(path.endsWith('/gyms/1/members/2'))body={id:2,name:'Member Fixture',memberships:[],bookings:[{id:9,date:'2027-01-01',status:'CONFIRMED',quantity:1}],visits:[],booking_total:1,visit_total:0}
  else if(path.endsWith('/users/me')&&request.method==='PATCH'){if(failProfile){status=400;body={detail:'Profile rejected by fixture'}}else{body={user,reauthenticate:false}}}
  else if(path.endsWith('/admin/audit-logs'))body={items:[{id:'GYM_REVIEW:1',actor_id:1,resource_type:'GYM_REVIEW',resource_id:1,timestamp:'2026-11-01T00:00:00Z',action:'STATUS_CHANGE',context:{from:'DRAFT',to:'APPROVED'}}],total:1}
  else if(path.endsWith('/admin/settings'))body={payment:{enabled:true,provider:'CASHFREE',mode:'test',wallet_test_credit:false},limitations:{refunds:'Cancellation does not initiate a refund.'}}
  else if(path.endsWith('/notifications/preferences'))body={enabled:false,operational_email:false,email_available:false,message:'Disabled fixture'}
  else if(path.endsWith('/meta/support'))body={email:null,message:'No configured contact'}
  else if(path.endsWith('/admin/ping'))body={status:'ok',user_id:1}
  else throw Error(`Unexpected API ${request.method} ${path}`)
  await command('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
 }catch(error){errors.push(error.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'})}
}
async function page(path,text){await command('Page.navigate',{url:origin+path});await until(`document.body.innerText.includes(${JSON.stringify(text)})`);for(const width of [360,768,1440]){await command('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:width<640});assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),true,path)}}
try{
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await command('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('fitigo:access_token','phase5-fixture')"})
 await page('/owner/bookings/9','Action availability')
 assert.equal(await evaluate("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Mark attended')"),false)
 await click('Cancel booking');await until("!!document.querySelector('dialog[open]')");await click('Confirm update','dialog button');await until("document.body.innerText.includes('CANCELLED') || document.body.innerText.includes('Cancelled')");assert.equal(cancelled,true)
 await page('/owner/members','Member Fixture');await click('View gym history');await until("document.body.innerText.includes('Verified visits')")
 await page('/owner/settings','Save profile');await click('Save profile');await until("document.body.innerText.includes('Profile rejected by fixture')");assert.equal(await evaluate("document.body.innerText.includes('Profile saved.')"),false)
 failProfile=false;await click('Save profile');await until("document.body.innerText.includes('Profile saved.')")
 await page('/owner/help','owners may scan for their own gyms')
 role='ADMIN';await page('/admin/audit-logs','STATUS CHANGE');await page('/admin/settings','CASHFREE');await page('/admin/profile','Save profile')
 assert.deepEqual(errors,[]);console.log('PASS owner action eligibility, profile failure/success, gym history, help, protected audit/settings UI, 360/768/1440 layouts')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await target.dispose()}