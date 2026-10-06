// TEST ONLY: intercepted responses and isolated storage; never writes live records.
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const target=await isolatedBrowserTarget()
const ws=new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
let sequence=0,role='CUSTOMER',failure=null,delay=false,previewWrites=0,confirmWrites=0
const pending=new Map(),errors=[],writes=[]
const user={id:1,first_name:'Pause',last_name:'Fixture',email:'pause@example.test',phone:null}
const start='2026-11-01T00:00:00Z',end='2026-12-01T00:00:00Z'
let member={id:1,user_id:1,gym_id:null,plan_id:null,membership_type:'MULTI_GYM',platform_plan_id:1,status:'ACTIVE',start_at:start,end_at:end,paid_amount:'1200.00',currency:'INR',payment_provider:'WALLET',payment_status:'PAID',terms_snapshot:{name:'Pause fixture plan',duration_value:1,duration_unit:'MONTH'}}
let eligibility={membership_id:1,membership_status:'ACTIVE',pause_allowed:true,can_pause:true,max_pause_days:9,pause_days_used:3,pause_days_remaining:6,currently_paused:false,eligible_from:'2026-11-10',eligible_until:'2026-11-30',original_end_at:end,current_end_at:end,current_pause:null,history:[],reason_code:null,timezone:'UTC'}
const preview={membership_id:1,start_date:'2026-11-10',end_date:'2026-11-13',resumes_on:'2026-11-14',days:4,current_end_at:end,new_end_at:'2026-12-05T00:00:00Z',pause_days_remaining_after:2,preview_token:'a'.repeat(64)}
let platform={id:1,code:'pause-fixture',name:'Pause fixture plan',membership_type:'MULTI_GYM',description:null,duration_value:1,duration_unit:'MONTH',base_price:'1200.00',final_price:'1200.00',discount_amount:'0.00',discount_percentage:null,currency:'INR',offer:null,benefits:[],badge:null,display_order:1,is_active:true,version:1,pause_rule:{allowed:true,max_pause_days:9},access_rule:{scope:'ELIGIBLE_PARTNER_GYMS',daily_access:1},purchase_available:false}
let ownerPlan={id:1,gym_id:1,name:'Single pause fixture',description:null,duration_days:30,price:'600.00',currency:'INR',is_active:true,pause_policy:{allowed:true,max_pause_days:6}}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>reject(Error(method)),20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms))
async function until(expression){for(let i=0;i<140;i++){if(await evaluate(expression))return;await wait(70)}throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`)}
async function click(text,selector='button'){await until(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).some(b=>b.textContent.trim()===${JSON.stringify(text)})`);await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`);await wait(90)}
async function fill(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}))})()`);await wait(50)}
async function visit(path,text){await command('Page.navigate',{url:'http://localhost:5173'+path});await wait(200);await until(`document.body.innerText.includes(${JSON.stringify(text)})`)}
async function width(w){await command('Emulation.setDeviceMetricsOverride',{width:w,height:850,deviceScaleFactor:1,mobile:w<768});await wait(90);assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),true)}
async function screenshot(name){const image=await command('Page.captureScreenshot',{format:'png'});await writeFile(join(tmpdir(),name),Buffer.from(image.data,'base64'))}
async function checkPauseCard(){
 const layout=await evaluate(`(()=>{const pause=document.querySelector('.fm-pause-card'),plan=document.querySelector('.fm-membership-card'),section=pause?.querySelector('.fm-pause-section');if(!pause||!plan||!section)return null;const p=pause.getBoundingClientRect(),m=plan.getBoundingClientRect(),ps=getComputedStyle(pause),ms=getComputedStyle(plan);return {sameSurface:ps.backgroundColor===ms.backgroundColor,sameBorder:ps.border===ms.border,sameRadius:ps.borderRadius===ms.borderRadius,samePadding:ps.padding===ms.padding,aligned:Math.abs(p.left-m.left)<1&&Math.abs(p.width-m.width)<1,separated:p.top-m.bottom>=19,noDoubleDivider:getComputedStyle(section).borderTopWidth==='0px',named:section.getAttribute('aria-label')==='Membership pause'}})()`)
 assert.ok(layout,'Pause is inside a membership panel')
 for(const [name,value] of Object.entries(layout))assert.equal(value,true,name)
 const placement=await evaluate(`(()=>{const pause=document.querySelector('.fm-primary-pause .fm-pause-card'),links=document.querySelector('.fm-membership-links'),access=document.querySelector('.fm-current-access');if(!pause||!links||!access)return null;const p=pause.getBoundingClientRect(),l=links.getBoundingClientRect(),a=access.getBoundingClientRect();return innerWidth>=768 ? {sameRow:Math.abs(p.top-l.top)<1,beside:l.left>=p.right,belowAccess:l.top>=a.bottom+19} : {stacked:Math.abs(p.left-l.left)<1,accessAfterPause:a.top>=p.bottom+19,linksAfterAccess:l.top>=a.bottom+19}})()`)
 assert.ok(placement,'Primary pause and links have dedicated grid cells')
 for(const [name,value] of Object.entries(placement))assert.equal(value,true,name)
}
function fixture(request){
 const path=new URL(request.url).pathname
 if(path==='/api/v1/auth/session')return {user,roles:[role]}
 if(path==='/api/v1/users/me')return user
 if(path==='/api/v1/users/me/roles')return [role]
 if(path==='/api/v1/memberships/me')return [member]
 if(path==='/api/v1/profile/membership')return {membership_id:1,plan_name:member.terms_snapshot.name,status:member.status,start_date:start,end_date:member.end_at,membership_scope:member.membership_type,active_gyms:[],membership_features:[]}
 if(path==='/api/v1/customer/access-calendar')return {access_type:member.membership_type,gym:null,days:[]}
 if(path==='/api/v1/memberships/me/1/pause/preview') {previewWrites++;assert.deepEqual(JSON.parse(request.postData),{start_date:preview.start_date,days:preview.days});return preview}
 if(path==='/api/v1/memberships/me/1/pause') {
  if(request.method==='POST'){
   confirmWrites++;const body=JSON.parse(request.postData);writes.push({path,body,headers:request.headers});assert.deepEqual(body,{start_date:preview.start_date,days:preview.days,accepted_preview:preview.preview_token})
   eligibility={...eligibility,pause_days_used:7,pause_days_remaining:2,current_end_at:preview.new_end_at,history:[{...preview,id:1,status:'SCHEDULED',previous_end_at:end}]};member={...member,end_at:preview.new_end_at}
  }return eligibility
 }
 if(path==='/api/v1/gym-owner/gyms')return [{id:1,name:'Pause fixture gym',status:'APPROVED',is_active:true}]
 if(path==='/api/v1/gym-owner/gyms/1/membership-plans')return [ownerPlan]
 if(path==='/api/v1/gym-owner/membership-plans/1'){const body=JSON.parse(request.postData);writes.push({path,body});ownerPlan={...ownerPlan,...body};return ownerPlan}
 if(path==='/api/v1/admin/membership-plans')return {items:[platform],server_time:start,checkout_available:false}
 if(path==='/api/v1/admin/membership-plans/1'){
  if(request.method==='PUT'){const body=JSON.parse(request.postData);writes.push({path,body});platform={...platform,...body,version:platform.version+1};return platform}
  return {plan:platform,offer_configuration:null,server_time:start}
 }
 if(path==='/api/v1/memberships/gyms/1/plans')return [ownerPlan]
 if(path==='/api/v1/gyms/1/details')return {gym_id:1,gym_name:'Pause fixture gym',images:[],location:{city:'Test city'},opening_hours:{weekly:[]}}
 throw Error(`Unexpected ${request.method} ${path}`)
}
ws.onmessage=async event=>{
 const m=JSON.parse(event.data),p=pending.get(m.id)
 if(p){clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
 if(m.method==='Fetch.requestPaused'){
  const {requestId,request}=m.params
  try{
   if(delay&&request.url.includes('/pause'))await wait(450)
   if(failure&&request.url.includes(failure.path)&&request.method===failure.method){
    if(failure.status===0){await command('Fetch.failRequest',{requestId,errorReason:'ConnectionFailed'});return}
    await command('Fetch.fulfillRequest',{requestId,responseCode:failure.status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify({detail:{code:failure.code||'SQL_PRIVATE_ERROR'}})).toString('base64')});return
   }
   const body=fixture(request);await command('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
  }catch(e){if(!e.message.includes('Invalid InterceptionId'))errors.push(e.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'}).catch(()=>{})}
 }
}
try{
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await command('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.setItem('fitigo:access_token','pause-fixture');localStorage.setItem('fitigo:refresh_token','fixture');`})
 delay=true;await command('Page.navigate',{url:'http://localhost:5173/membership/1'});await until(`!!document.querySelector('.fm-pause-section [aria-label="Loading"]')`);await until(`document.body.innerText.includes('Pause Membership')`);delay=false
 for(const w of [360,375,390,430,768,1024,1280,1440]){await width(w);await checkPauseCard()}
 await screenshot('fitigo-pause-card-desktop.png');await width(390);await screenshot('fitigo-pause-card-mobile.png')
 await click('Pause Membership');await until(`!!document.querySelector('input[name="pause_start"]')`)
 assert.equal(await evaluate(`document.querySelector('input[name="pause_start"]').min`),eligibility.eligible_from)
 assert.equal(await evaluate(`document.querySelector('input[name="pause_days"]').max`),'6')
 await fill('input[name="pause_days"]','7');assert.equal(await evaluate(`document.querySelector('dialog form').checkValidity()`),false)
 await fill('input[name="pause_days"]','4');await click('Review Pause');await until(`document.body.innerText.includes('New expiry')`)
 assert.equal(previewWrites,1)
 for(const w of [360,390,768,1440])await width(w)
 await screenshot('fitigo-pause-preview-desktop.png');await width(390);await screenshot('fitigo-pause-preview-mobile.png')
 assert.equal(await evaluate(`document.querySelector('dialog').innerText.includes('05 Dec 2026')`),true)
 failure={path:'/pause',method:'POST',status:0};await click('Confirm Pause');await until(`document.body.innerText.includes('Unable to pause your membership')`);assert.equal(confirmWrites,0)
 failure=null;delay=true;await evaluate(`(()=>{const f=document.querySelector('dialog form');f.requestSubmit();f.requestSubmit()})()`);await until(`document.body.innerText.includes('Pause scheduled')`);delay=false
 assert.equal(confirmWrites,1);assert.equal(await evaluate(`document.querySelector('dialog').innerText.includes('remains active until')`),true)
 await click('View Membership');await until(`!document.querySelector('dialog') && document.body.innerText.includes('Pause History')`)
 await visit('/membership/1/details','Pause History');await evaluate(`document.querySelector('.fm-pause-history').open=true`);await until(`document.body.innerText.includes('Scheduled') || document.body.innerText.includes('scheduled')`)
 console.log('PASS backend allowance/date bounds, responsive selection and preview, network failure, duplicate prevention, authoritative dates, history and refresh')
 eligibility={...eligibility,membership_status:'PAUSED',currently_paused:true,can_pause:false,current_pause:eligibility.history[0],reason_code:'MEMBERSHIP_ALREADY_PAUSED'};member.status='PAUSED'
 await visit('/membership','Membership Paused');assert.equal(await evaluate(`!!document.querySelector('.fm-membership-choices')`),false)
 await checkPauseCard()
 assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Pause Membership')`),false)
 member={...member,membership_type:'SINGLE_GYM',gym_id:1,plan_id:1,status:'ACTIVE'};eligibility={...eligibility,membership_status:'ACTIVE',currently_paused:false,current_pause:null,can_pause:true,reason_code:null}
 await visit('/membership/1','Pause Membership');eligibility={...eligibility,can_pause:false,pause_allowed:false,reason_code:'PAUSE_NOT_ALLOWED'}
 await click('Refresh pause policy');await until(`document.body.innerText.includes('Pause unavailable for this membership plan')`)
 await checkPauseCard();assert.equal(await evaluate(`document.querySelector('.fm-pause-unavailable').innerText.includes('Pause unavailable')`),true)
 await width(1440);await checkPauseCard();await screenshot('fitigo-pause-unavailable-desktop.png');await width(390);await checkPauseCard();await screenshot('fitigo-pause-unavailable-mobile.png')
 assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent.trim()==='Pause Membership')`),false)
 failure={path:'/pause',method:'GET',status:500};await visit('/membership/1','Unable to load your membership information');assert.equal(await evaluate(`document.body.innerText.includes('SQL_PRIVATE')`),false);failure=null;await click('Try again');await until(`document.body.innerText.includes('Pause unavailable')`)
 console.log('PASS paused/disabled/Single-Gym states, live policy refresh, sanitized technical error and retry')
 await visit('/membership/pause','Pause unavailable');assert.equal(await evaluate(`document.querySelectorAll('.fm-panel .fm-panel').length`),0)
 console.log('PASS matching pause cards, desktop/mobile alignment and standalone pause page without nested cards')
 role='ADMIN';await visit('/admin/membership-plans/1','Pause policy');await width(390)
 await fill('input[name="max_pause_days"]','13');await click('Review Changes');await click('Confirm Save');await until(`location.pathname==='/admin/membership-plans'`)
 assert.deepEqual(writes.at(-1).body.pause_rule,{allowed:true,max_pause_days:13})
 role='GYM_OWNER';await visit('/owner/gyms/1/memberships/1/edit','Pause policy');await width(360)
 await fill('input[name="max_pause_days"]','8');await evaluate(`document.querySelector('main form').requestSubmit()`);await until(`location.pathname==='/owner/gyms/1/memberships'`)
 assert.deepEqual(writes.at(-1).body.pause_policy,{allowed:true,max_pause_days:8})
 await visit('/owner/gyms/1/memberships/1/edit','Pause policy');await evaluate(`document.querySelector('input[name="pause_allowed"]').click()`)
 assert.equal(await evaluate(`document.querySelector('input[name="max_pause_days"]').disabled`),true)
 await evaluate(`document.querySelector('main form').requestSubmit()`);await until(`location.pathname==='/owner/gyms/1/memberships'`)
 assert.deepEqual(writes.at(-1).body.pause_policy,{allowed:false,max_pause_days:0})
 assert.deepEqual(errors,[])
 console.log('PASS Admin/Owner existing plan editors persist policy, disable limits appropriately, mobile layouts and no browser exceptions')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await target.dispose()}