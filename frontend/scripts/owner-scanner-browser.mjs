// Isolated camera/API fixtures; real jsQR decoding and canvas video playback.
// Does not create real check-ins or use real credentials.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin=process.env.FITIGO_TEST_ORIGIN||'http://localhost:5173', debug='http://localhost:9231'
const target=await isolatedBrowserTarget(debug)
const ws=new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
let sequence=0, responseMode='CHECKED_IN', responseDelay=300
const pending=new Map(), failures=[], exceptions=[], calls=[]
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(Error(method)),20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result.value}
const wait=ms=>new Promise(r=>setTimeout(r,ms))
async function until(expression){for(let i=0;i<200;i++){if(await evaluate(expression))return;await wait(100)}throw Error(`Not ready ${expression}: ${await evaluate('document.body?.innerText')}`)}
const state=()=>evaluate(`document.querySelector('[data-scanner-state]')?.dataset.scannerState`)
async function isState(value){await until(`document.querySelector('[data-scanner-state]')?.dataset.scannerState===${JSON.stringify(value)}`)}
async function click(text){await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`);await wait(50)}
async function show(token){await evaluate(`window.testDraw(${JSON.stringify(token)})`)}
ws.onmessage=async event=>{
 const m=JSON.parse(event.data)
 if(pending.has(m.id)){const p=pending.get(m.id);clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result)}
 if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails.text)
 if(m.method==='Fetch.requestPaused'){
  const {requestId,request}=m.params
  try{
   const path=new URL(request.url).pathname;let body
   if(path.endsWith('/auth/session'))body={user:{id:9001,first_name:'Scanner',last_name:'Test',email:'scanner@example.test',phone:null},roles:['GYM_STAFF']}
   else if(path.endsWith('/users/me'))body={id:9001,first_name:'Scanner',last_name:'Test',email:'scanner@example.test',phone:null}
   else if(path.endsWith('/users/me/roles'))body=['GYM_STAFF']
   else if(path.endsWith('/gym-staff/gyms'))body=[{id:19,name:'Scanner Fixture Gym',city:'Test City'}]
   else if(path.endsWith('/checkins/validate')){
    assert.equal(request.method,'POST');calls.push(JSON.parse(request.postData))
    const mode=responseMode;await wait(responseDelay)
    if(mode==='NETWORK'){await command('Fetch.failRequest',{requestId,errorReason:'ConnectionFailed'});return}
    if(mode==='SERVER'){await command('Fetch.fulfillRequest',{requestId,responseCode:500,body:Buffer.from('{"detail":"SQL private failure"}').toString('base64')});return}
    body=mode==='CHECKED_IN'?{success:true,status:'CHECKED_IN',customer_name:'Fixture Member',gym_name:'Scanner Fixture Gym',access_type:'MULTI_GYM',checkin_time:new Date().toISOString()}:mode==='MALFORMED'?{success:true,status:'OK'}:{success:false,status:mode,message:'SQL private failure'}
   }else throw Error(`Unexpected API ${path}`)
   await command('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify(body)).toString('base64')})
  }catch(e){if(e.message.includes('Invalid InterceptionId'))return;failures.push(e.message);await command('Fetch.failRequest',{requestId,errorReason:'Failed'}).catch(()=>{})}
 }
}
try{
 await command('Runtime.enable');await command('Page.enable');await command('Fetch.enable',{patterns:[{urlPattern:'*/api/v1/*'}]})
 await command('Page.addScriptToEvaluateOnNewDocument',{source:`
  localStorage.setItem('fitigo:access_token','isolated-scanner-fixture');
  Object.defineProperty(window,'BarcodeDetector',{value:undefined,configurable:true});
  const params=new URLSearchParams(location.search);
  window.testStreams=[];window.testRequests=0;window.testCameraError=params.get('error')||'';window.testDelay=Number(params.get('delay')||0);
  window.testPermission={state:params.get('permission')||'granted',onchange:null};
  navigator.permissions.query=async()=>window.testPermission;
  navigator.mediaDevices.getUserMedia=async constraints=>{
   window.testRequests++;window.testConstraints=constraints;
   if(window.testCameraError)throw new DOMException('Fixture camera failure',window.testCameraError);
   const canvas=document.createElement('canvas');canvas.width=canvas.height=410;
   const graphics=canvas.getContext('2d');graphics.fillStyle='white';graphics.fillRect(0,0,410,410);
   window.testDraw=async value=>{
    graphics.fillStyle='white';graphics.fillRect(0,0,410,410);
    if(value){const {accessQrMatrix}=await import('/src/components/accessQrMatrix.ts');graphics.fillStyle='black';accessQrMatrix(value).forEach((row,y)=>row.forEach((dark,x)=>{if(dark)graphics.fillRect((x+4)*10,(y+4)*10,10,10)}))}
   };
   const stream=canvas.captureStream(10);window.testStreams.push(stream);
   const tick=setInterval(()=>{graphics.drawImage(canvas,0,0);if(stream.getTracks().every(t=>t.readyState==='ended'))clearInterval(tick)},80);
   if(window.testDelay)await new Promise(r=>setTimeout(r,window.testDelay));
   return stream;
  };
 `})
 async function visit(query=''){await command('Page.navigate',{url:origin+'/owner/check-in'+query});await until(`!!document.querySelector('[data-scanner-state]')`)}
 await visit();await isState('SCANNING')
 assert.equal(await evaluate('typeof BarcodeDetector'),'undefined');assert.equal(await evaluate('window.testRequests'),1)
 assert.equal(await evaluate('window.testConstraints.video.facingMode.ideal'),'environment')
 await evaluate(`window.originalVideo=document.querySelector('video');window.originalStream=window.originalVideo.srcObject`)
 await show('GYMACCESS:first-fixture');await isState('VALIDATING');assert.equal(calls.length,1)
 await isState('APPROVED');assert.equal(await evaluate(`document.body.innerText.includes('ACCESS APPROVED')`),true)
 await isState('SCANNING');await wait(3500);assert.equal(calls.length,1,'Stationary QR must not resubmit after cooldown')
 assert.equal(await evaluate(`document.querySelector('video')===window.originalVideo && window.originalVideo.srcObject===window.originalStream && window.originalStream.getTracks()[0].readyState==='live'`),true)
 await show('GYMACCESS:second-fixture');await isState('APPROVED');assert.equal(calls.length,2);await isState('SCANNING')
 responseMode='QR_ALREADY_USED';await show(null);await wait(900);await show('GYMACCESS:first-fixture');await isState('REJECTED');await isState('SCANNING')
 console.log('PASS auto-start, real decoder, persistent video/stream, two consecutive members, stationary suppression, deliberate QR reuse rejection')
 for(const code of ['DAILY_ACCESS_ALREADY_CONSUMED','MEMBERSHIP_EXPIRED','MEMBERSHIP_PAUSED','WRONG_GYM','INVALID_QR']){
  responseMode=code;await show('GYMACCESS:fixture-'+code);await isState('REJECTED')
  assert.equal(await evaluate(`document.body.innerText.includes('SQL')`),false)
  await isState('SCANNING')
 }
 for(const mode of ['NETWORK','SERVER','MALFORMED']){
  responseMode=mode;await show('GYMACCESS:technical-'+mode)
  await until(`document.querySelector('.ow-scan-overlay')?.innerText.includes('Unable to verify access')`)
  assert.equal(await state(),'SCANNING');assert.equal(await evaluate(`document.body.innerText.includes('ACCESS REJECTED')`),false)
  await until(`!!document.querySelector('.ow-scan-ready')`)
 }
 responseMode='CHECKED_IN';responseDelay=14000;await show('GYMACCESS:timeout-fixture')
 await isState('VALIDATING');await until(`document.querySelector('.ow-scan-overlay')?.innerText.includes('Unable to verify access')`)
 assert.equal(await state(),'SCANNING');await until(`!!document.querySelector('.ow-scan-ready')`);responseDelay=300
 await show('GYMACCESS:after-timeout');await isState('APPROVED');await isState('SCANNING')
 assert.equal(await evaluate('window.testRequests'),1,'No camera restart per scan')
 console.log('PASS business rejections, network/server/malformed/timeout handling, automatic recovery without restarting camera')
 for(const width of [360,390,768,1024,1440]){await command('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:width<640});assert.equal(await evaluate(`document.documentElement.scrollWidth<=document.documentElement.clientWidth+1`),true)}
 await show(null);await evaluate(`const track=window.originalStream.getTracks()[0];track.stop();track.dispatchEvent(new Event('ended'))`);await isState('CAMERA_ERROR')
 await click('Try Again');await isState('SCANNING')
 await evaluate(`window.testPermission.state='denied';window.testPermission.onchange()`);await isState('PERMISSION_REQUIRED')
 assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`),true)
 await evaluate(`window.testPermission.state='granted';window.testPermission.onchange()`);await isState('SCANNING')
 await visit('?permission=denied');await isState('PERMISSION_REQUIRED');await wait(500);assert.equal(await evaluate('window.testRequests'),0)
 await evaluate(`window.testCameraError='NotAllowedError'`);await click('Allow Camera');await until(`document.body.innerText.includes('browser settings')`);await wait(600);assert.equal(await evaluate('window.testRequests'),1)
 await evaluate(`window.testCameraError='';window.testPermission.state='granted';window.testPermission.onchange()`);await isState('SCANNING')
 await visit('?permission=prompt');await isState('SCANNING');assert.equal(await evaluate('window.testRequests'),1)
 for(const error of ['NotFoundError','NotReadableError']){await visit('?error='+error);await isState('CAMERA_ERROR');await evaluate(`window.testCameraError=''`);await click('Try Again');await isState('SCANNING')}
 console.log('PASS responsive scanner, camera loss/retry, permission prompt/denial/revocation/grant, missing/busy camera')
 await click('Stop camera');await isState('CAMERA_ERROR');responseMode='CHECKED_IN'
 await evaluate(`document.querySelector('details').open=true;const input=document.querySelector('details input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'manual-fixture');input.dispatchEvent(new Event('input',{bubbles:true}))`)
 await wait(60);const beforeManual=calls.length;await evaluate(`const form=document.querySelector('details form');form.requestSubmit();form.requestSubmit()`)
 await isState('APPROVED');assert.equal(calls.length,beforeManual+1);await isState('CAMERA_ERROR')
 await click('Try Again');await isState('SCANNING');responseDelay=800
 await show('GYMACCESS:leaving-fixture');await isState('VALIDATING');await evaluate(`document.querySelector('a[href="/owner/settings"]').click()`)
 await until(`!document.querySelector('video')`);await wait(1100)
 assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`),true)
 await visit('?delay=1000');await until(`window.testStreams.length===1`);await evaluate(`document.querySelector('a[href="/owner/settings"]').click()`);await wait(1300)
 assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`),true)
 assert.deepEqual(failures,[]);assert.deepEqual(exceptions,[])
 console.log('PASS manual token, duplicate submit protection, pending API/unmount cleanup and late camera initialization cleanup')
}finally{await command('Fetch.disable').catch(()=>{});ws.close();await target.dispose()}