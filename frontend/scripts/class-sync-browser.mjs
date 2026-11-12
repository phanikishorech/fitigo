// Mocked HTTP only. No real class edits, bookings, payments or user credentials.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin=process.env.FITIGO_TEST_ORIGIN||'http://localhost:5173'
const target=await isolatedBrowserTarget(),ws=new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
let sequence=0,blocked=true,mutations=0
const pending=new Map(),errors=[]
const slot={id:9,gym_id:1,name:'Fixture class',start_time:'14:00:00',end_time:'15:00:00',capacity:10,price:'100.00',is_active:true}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms))
async function until(expression){for(let i=0;i<100;i++){if(await evaluate(expression))return;await wait(80)}throw Error(await evaluate('document.body.innerText'))}
async function click(text,selector='button'){await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el=>el.textContent.trim()===${JSON.stringify(text)}).click()`)}
ws.onmessage=async event=>{
 const m=JSON.parse(event.data),p=pending.get(m.id)
 if(p){pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
 if(m.method!=='Fetch.requestPaused')return
 const {requestId,request}=m.params,path=new URL(request.url).pathname
 try{
  let body,status=200
  if(path.endsWith('/auth/session'))body={user:{id:1,first_name:'Owner',email:'owner@example.com'},roles:['GYM_OWNER']}
  else if(path.endsWith('/gym-owner/gyms'))body=[{id:1,name:'Fixture gym',status:'APPROVED',is_active:true}]
  else if(path.endsWith('/gym-owner/gyms/1/slots'))body=[slot]
  else if(path.endsWith('/gym-owner/slots/9')&&request.method==='DELETE'){
   mutations++
   if(blocked){status=409;body={detail:{code:'CLASS_HAS_RESERVATIONS',message:'No changes saved'}}}
   else{slot.is_active=false;body={status:'ok'}}
  }else throw Error(`Unexpected API ${request.method} ${path}`)
  await command('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
 }catch(error){errors.push(error.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'})}
}
try{
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await command('Page.addScriptToEvaluateOnNewDocument',{source:"localStorage.setItem('fitigo:access_token','isolated-class-fixture')"})
 await command('Page.navigate',{url:origin+'/owner/gyms/1/classes'})
 await until(`document.body.innerText.includes('Fixture class')`)
 assert.equal(await evaluate(`document.body.innerText.includes('Booked or payment-pending sessions block the whole change')`),true)
 for(const width of [360,768,1440]){await command('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:width<640});assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'),true)}
 await click('Deactivate');await until(`!!document.querySelector('dialog[open]')`);await click('Confirm change','dialog button')
 await until(`document.body.innerText.includes('No changes saved.')`)
 assert.equal(slot.is_active,true);assert.equal(mutations,1)
 blocked=false;await click('Confirm change','dialog button');await until(`!document.querySelector('dialog[open]') && document.body.innerText.includes('Activate')`)
 assert.equal(slot.is_active,false);assert.equal(mutations,2);assert.deepEqual(errors,[])
 console.log('PASS conservative class policy notice, 409 no-change state, successful retry and responsive owner layout')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await target.dispose()}