// Every API request is intercepted; no working account/data mutations.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin=process.env.FITIGO_TEST_ORIGIN||'http://127.0.0.1:5195'
const target=await isolatedBrowserTarget(),ws=new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
let seq=0,role='GYM_OWNER',cancelled=false,failProfile=true,removed=false,cleaned=false,deletes=0,opted=false,read=false,failPreference=true
const pending=new Map(),errors=[]
let ticket=null, ticketMessages=[], rejectCreate=true, rejectReply=true, capturedKeys=[]
const user={id:1,first_name:'Fixture',last_name:'Owner',email:'owner@example.com',phone:null}
const booking={id:9,gym_id:1,gym_slot_id:1,slot_date:'2027-01-01',quantity:1,total_price:'100',currency:'INR',status:'CONFIRMED',created_at:'2026-11-01T00:00:00Z',attendance_status:null,attendance_marked_at:null,customer:{id:2,first_name:'Member',last_name:'Fixture'},slot:{id:1,name:'Visit',start_time:'14:00',end_time:'15:00'},payment:{status:'PAID'},allowed_actions:['CANCEL'],action_unavailable_reasons:{MARK_ATTENDED:'Use QR check-in.',MARK_NO_SHOW:'Admission window is open.'}}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}
async function until(expression){for(let i=0;i<600;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,80))}throw Error(JSON.stringify({expression,body:await evaluate('document.body.innerText'),errors}))}
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
  else if(path.endsWith('/gym-owner/gyms/1'))body={id:1,name:'Fixture gym',status:'APPROVED',is_active:true,images:removed?[]:[{id:1,file_path:'fixture.png',original_filename:'Fixture photo',is_cover:true,display_order:0}],facilities:[],operating_hours:[],created_at:'2026-11-01T00:00:00Z'}
  else if(path.endsWith('/gyms/1/image-deletions'))body={enabled:true,items:removed&&!cleaned?[{job_id:1,image_id:1,status:'PENDING',file_deleted:false,error_code:'STORAGE_UNAVAILABLE'}]:[]}
  else if(path.endsWith('/gyms/1/images/1')&&request.method==='DELETE'){removed=true;deletes++;body={job_id:1,image_id:1,status:'PENDING',file_deleted:false,error_code:'STORAGE_UNAVAILABLE'}}
  else if(path.endsWith('/gyms/1/image-deletions/1/retry')){cleaned=true;body={job_id:1,image_id:1,status:'COMPLETE',file_deleted:true,error_code:null}}
  else if(path.endsWith('/gym-owner/bookings/9'))body=booking
  else if(path.endsWith('/gym-owner/bookings/9/cancel')){cancelled=true;booking.status='CANCELLED';booking.allowed_actions=[];body=booking}
  else if(path.endsWith('/gyms/1/members'))body={items:[{id:2,name:'Member Fixture',membership_status:'ACTIVE'}],total:1}
  else if(path.endsWith('/gyms/1/members/2'))body={id:2,name:'Member Fixture',memberships:[],bookings:[{id:9,date:'2027-01-01',status:'CONFIRMED',quantity:1}],visits:[],booking_total:1,visit_total:0}
  else if(path.endsWith('/users/me')&&request.method==='PATCH'){if(failProfile){status=400;body={detail:'Profile rejected by fixture'}}else{body={user,reauthenticate:false}}}
  else if(path.endsWith('/admin/audit-logs'))body={items:[{id:'GYM_REVIEW:1',actor_id:1,resource_type:'GYM_REVIEW',resource_id:1,timestamp:'2026-11-01T00:00:00Z',action:'STATUS_CHANGE',context:{from:'DRAFT',to:'APPROVED'}}],total:1}
  else if(path.endsWith('/admin/settings'))body={payment:{enabled:true,provider:'CASHFREE',mode:'test',wallet_test_credit:false},limitations:{refunds:'Cancellation does not initiate a refund.'}}
  else if(path.endsWith('/notifications/preferences')){
   if(request.method==='PATCH'){if(failPreference){status=409;body={detail:'Channel unavailable fixture'}}else{opted=JSON.parse(request.postData).operational_email;body={enabled:true,operational_email:opted,email_available:true,message:'Operational email is opt-in.'}}}
   else body={enabled:true,operational_email:opted,email_available:true,message:'Operational email is opt-in.'}
  }
  else if(path.endsWith('/notifications/inbox'))body={enabled:true,items:[{id:1,title:'Booking cancelled',body:'Cancellation does not initiate a refund.',category:'OPERATIONAL',created_at:'2026-11-01T00:00:00Z',read_at:read?'2026-11-02T00:00:00Z':null,email_status:'UNKNOWN',error_code:'PROVIDER_ACCEPTANCE_UNCERTAIN'}],total:1,unread_count:read?0:1}
  else if(path.endsWith('/notifications/inbox/1/read')){read=true;body={id:1,read_at:'2026-11-02T00:00:00Z'}}
  else if(path.endsWith('/notifications/delivery-status'))body={enabled:true,items:[],total:0}
  else if(path.endsWith('/meta/support'))body={email:null,message:'No configured contact',ticketing_available:true}
  else if(path.endsWith('/support/tickets')&&request.method==='POST'){
   capturedKeys.push(Object.entries(request.headers).find(([key])=>key.toLowerCase()==='idempotency-key')?.[1])
   if(rejectCreate){status=409;body={detail:'Fixture request rejected'}}
   else{const data=JSON.parse(request.postData);ticket={id:1,user_id:1,category:data.category,subject:data.subject,status:'OPEN',version:1,updated_at:'2026-11-11T00:00:00Z'};ticketMessages=[{id:1,author_kind:'REQUESTER',body:data.body,created_at:'2026-11-11T00:00:00Z'}];body=ticket}
  }
  else if(path.endsWith('/support/tickets'))body={items:ticket?[ticket]:[],total:ticket?1:0}
  else if(path.endsWith('/support/tickets/1/messages')){
   if(rejectReply){status=409;body={detail:'Conversation changed. Refresh before replying.'}}
   else{const data=JSON.parse(request.postData);ticketMessages.push({id:ticketMessages.length+1,author_kind:role==='ADMIN'?'ADMIN':'REQUESTER',body:data.body,created_at:'2026-11-11T00:00:00Z'});ticket.version++;body=ticket}
  }
  else if(path.endsWith('/support/tickets/1/status')){ticket.status=JSON.parse(request.postData).status;ticket.version++;body=ticket}
  else if(path.endsWith('/support/tickets/1'))body={...ticket,messages:ticketMessages,message_total:ticketMessages.length,can_reply:ticket.status!=='RESOLVED',can_change_status:role==='ADMIN'}
  else if(path.endsWith('/admin/readiness'))body={checks:[{code:'WORKER_SCHEDULING',status:'MANUAL_CHECK',message:'Verify scheduler separately.'}],queue_counts:{},production_certified:false,message:'Read-only observations.'}
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
 await page('/owner/notifications','Enable operational email');await click('Enable operational email');await until("document.body.innerText.includes('Channel unavailable fixture')");assert.equal(opted,false)
 failPreference=false;await click('Enable operational email');await until("document.body.innerText.includes('Turn off operational email')");assert.equal(opted,true)
 await until("document.body.innerText.includes('Mark read')");await click('Mark read');await until("document.body.innerText.includes('0 unread')");assert.equal(read,true)
 assert.equal(await evaluate("document.body.innerText.includes('Uncertain sends are not automatically resent')"),true)
 await page('/owner/help','owners may scan for their own gyms')
 await until("document.body.innerText.includes('Create a support request')")
 await evaluate("document.querySelector('summary').click()")
 await evaluate("document.querySelector('input[name=subject]').value='Fixture support';document.querySelector('textarea[name=body]').value='A private fixture issue'")
 await click('Submit support request');await until("document.body.innerText.includes('Fixture request rejected')");assert.equal(ticket,null)
 rejectCreate=false;await click('Submit support request');await until("document.body.innerText.includes('Request #1: Fixture support')")
 assert.equal(capturedKeys.length,2);assert.equal(capturedKeys[0],capturedKeys[1]);assert.ok(capturedKeys[0])
 for(const width of [360,768,1440]){await command('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:width<640});assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),true)}
 await page('/owner/gyms/1','Fixture gym');await until("Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Photos')");await click('Photos');await until("document.body.innerText.includes('Remove photo #1')")
 assert.equal(deletes,0);await click('Remove photo #1');await until("!!document.querySelector('dialog[open]')");assert.equal(deletes,0)
 for(const width of [360,768,1440]){await command('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:width<640});assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),true)}
 await click('Remove photo','dialog button');await until("document.body.innerText.includes('Retry file cleanup')");assert.equal(deletes,1)
 assert.equal(await evaluate("document.body.innerText.includes('Photo removed and stored file deleted.')"),false)
 await click('Retry file cleanup');await until("!document.body.innerText.includes('Retry file cleanup')");assert.equal(cleaned,true)
 role='ADMIN';await page('/admin/audit-logs','STATUS CHANGE');await page('/admin/settings','CASHFREE');await page('/admin/profile','Save profile');await page('/admin/notifications','Email processing status')
 await page('/admin/support','Support queue');await until("document.body.innerText.includes('Open request #1')");await click('Open request #1');await until("document.body.innerText.includes('Send reply')")
 await evaluate("const el=document.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(el,'Admin fixture reply');el.dispatchEvent(new Event('input',{bubbles:true}))")
 await click('Send reply');await until("document.body.innerText.includes('Conversation changed.')");assert.equal(ticketMessages.length,1)
 assert.equal(await evaluate("document.querySelector('textarea').value"),'Admin fixture reply')
 rejectReply=false;await click('Refresh conversation');await until("document.body.innerText.includes('Send reply')");await click('Send reply');await until("document.body.innerText.includes('Reply saved.')");assert.equal(ticketMessages.length,2)
 await until("document.body.innerText.includes('New status')")
 // Select the conversation status control rather than the header search category.
 await evaluate("(()=>{const el=Array.from(document.querySelectorAll('select')).find(s=>Array.from(s.options).some(o=>o.value==='RESOLVED'));el.value='RESOLVED';el.dispatchEvent(new Event('change',{bubbles:true}))})()")
 await click('Update request status');await until("document.body.innerText.includes('This request is resolved')");assert.equal(ticket.status,'RESOLVED')
 await page('/admin/readiness','Readiness checks');await until("document.body.innerText.includes('MANUAL CHECK')")
 assert.deepEqual(errors,[]);console.log('PASS private support creation/retry, admin reply conflict retention/resolution, readiness manual-check messaging, prior workflows and 360/768/1440 layouts')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await target.dispose()}