// Isolated owner-review fixtures. Never changes live gym records.
import assert from 'node:assert/strict'
const origin = 'http://localhost:5173', debug = 'http://localhost:9231'
const target = await (await fetch(`${debug}/json/new?${encodeURIComponent(origin)}`, {method:'PUT'})).json()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
let sequence=0, submissions=0, rejectSubmit=false
const pending=new Map(), errors=[]
const gym={id:1,owner_user_id:1,name:'Review Fixture',status:'REJECTED',is_active:false,rejection_reason:'Please correct your address. <script>not executable</script>',can_submit_for_approval:true,description:null,city:'Test City',state:null,phone:null,email:null,address_line_1:null,postal_code:null,gym_price_per_person:'100.00',has_classes:false,created_at:'2026-09-01T00:00:00Z',updated_at:'2026-09-01T00:00:00Z',images:[],facilities:[],operating_hours:[]}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(new Error(method)),20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms))
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await wait(100)}throw Error(`Not ready: ${expression}; ${await evaluate('document.body.innerText')}`)}
async function click(text,selector='button'){await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`);await wait(80)}
ws.onmessage=async event=>{
 const m=JSON.parse(event.data)
 if(pending.has(m.id)){const p=pending.get(m.id);clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
 if(m.method==='Fetch.requestPaused'){
  const {requestId,request}=m.params;const path=new URL(request.url).pathname;let body,code=200
  try{
   if(path.endsWith('/users/me'))body={id:1,first_name:'Owner',last_name:'Fixture',email:'owner@example.test',phone:null}
   else if(path.endsWith('/users/me/roles'))body=['GYM_OWNER']
   else if(path.endsWith('/gym-owner/gyms'))body=[gym]
   else if(path.endsWith('/facilities'))body=[]
   else if(path.endsWith('/gym-owner/gyms/1/submit')){
    assert.equal(request.method,'POST');submissions++;await wait(400)
    if(rejectSubmit){code=409;body={detail:'Gym status changed. Refresh and try again.'}}
    else {gym.status='PENDING_APPROVAL';gym.rejection_reason=null;gym.can_submit_for_approval=false;body={status:'ok',gym_id:1,new_status:gym.status}}
   }else if(path.endsWith('/gym-owner/gyms/1')){
    if(request.method==='PUT')Object.assign(gym,JSON.parse(request.postData));body=gym
   }else throw Error(`Unexpected API ${path}`)
   await command('Fetch.fulfillRequest',{requestId,responseCode:code,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
  }catch(e){errors.push(e.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'})}
 }
}
try{
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await command('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('fitigo:access_token','isolated-owner-review-fixture')"})
 await command('Page.navigate',{url:origin+'/owner/gyms/1'})
 await until(`document.body.innerText.includes('Reason: Please correct your address.')`)
 assert.equal(await evaluate(`document.querySelectorAll('main script').length`),0)
 for(const width of [360,390,768,1440]){
  await command('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<640})
  assert.equal(await evaluate(`document.documentElement.scrollWidth<=document.documentElement.clientWidth+1`),true)
 }
 await click('Edit details','a');await until(`!!document.querySelector('main form input')`)
 await evaluate(`const el=document.querySelector('main form input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'Corrected Fixture');el.dispatchEvent(new Event('input',{bubbles:true}))`)
 await wait(80);await click('Save changes');await until(`document.body.innerText.includes('Gym saved.')`)
 assert.equal(gym.name,'Corrected Fixture');assert.equal(gym.status,'REJECTED')
 await command('Page.navigate',{url:origin+'/owner/gyms/1'});await until(`document.body.innerText.includes('Reason: Please correct your address.')`)
 await click('Resubmit for approval');await until(`!!document.querySelector('dialog[open]')`)
 await click('Keep unchanged','dialog button');assert.equal(submissions,0)
 rejectSubmit=true;await click('Resubmit for approval');await click('Resubmit for approval','dialog button')
 await until(`document.querySelector('dialog')?.innerText.includes('Refresh')`);assert.equal(gym.status,'REJECTED')
 rejectSubmit=false
 await evaluate(`const b=Array.from(document.querySelectorAll('dialog button')).find(b=>b.textContent==='Resubmit for approval');b.click();b.click()`)
 await until(`document.body.innerText.includes('Your gym is being reviewed.')`)
 assert.equal(submissions,2,'one failed and one successful request, no duplicate')
 assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Resubmit for approval')`),false)
 assert.equal(await evaluate(`document.querySelector('main').innerText.includes('Reason:')`),false)
 assert.deepEqual(errors,[])
 console.log('PASS backend reason, safe text, responsive view, edit/save, cancel, failure/retry, duplicate prevention, pending refresh')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await fetch(`${debug}/json/close/${target.id}`)}