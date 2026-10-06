import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const source=readFileSync(new URL('../src/owner/scannerMachine.ts',import.meta.url),'utf8')
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const {scannerReducer:reduce,initialScannerState:initial,mayScan,normalizeCheckIn,RESULT_DISPLAY_MS,DUPLICATE_COOLDOWN_MS}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const scanning=()=>reduce(reduce(initial,{type:'CAMERA_PERMISSION_GRANTED'}),{type:'CAMERA_INITIALIZED'})
const approval={success:true,status:'CHECKED_IN',customer_name:'Member',gym_name:'Gym',access_type:'MULTI_GYM',checkin_time:'2026-10-01T12:00:00Z'}
const rejection={success:false,status:'QR_ALREADY_USED',message:'This QR has already been used.'}
test('pure reducer has exactly seven states and no effects or implicit clock',()=>{
 assert.doesNotMatch(source,/Date\.now\(|setTimeout\(|getUserMedia\(|\bfetch\(|navigate\(/)
 assert.equal(initial.state,'PERMISSION_REQUIRED');assert.equal(scanning().state,'SCANNING')
 assert.equal(scanning().cameraAttached,true);assert.equal(RESULT_DISPLAY_MS,2000);assert.equal(DUPLICATE_COOLDOWN_MS,2500)
})
test('invalid transitions cannot approve/reject/scan without initialized camera',()=>{
 for(const state of ['PERMISSION_REQUIRED','CAMERA_ERROR','SCANNING','APPROVED','REJECTED','CAMERA_READY']){
  const c={...initial,state}
  for(const type of ['VALIDATION_APPROVED','VALIDATION_REJECTED'])assert.equal(reduce(c,{type,cycle:0,result:type==='VALIDATION_APPROVED'?approval:rejection,at:100}),c)
 }
 assert.equal(reduce(initial,{type:'CAMERA_INITIALIZED'}),initial)
 const c=scanning();assert.equal(reduce(c,{type:'QR_DETECTED',qrValue:'',at:100}),c)
})
for(const success of [true,false])test(`scan → validate → ${success?'approve':'reject'} → scan is automatic and duplicate-safe`,()=>{
 const c=scanning();const v=reduce(c,{type:'QR_DETECTED',qrValue:'opaque-qr',at:100})
 assert.equal(v.state,'VALIDATING');assert.equal(v.isProcessingScan,true)
 assert.equal(reduce(v,{type:'QR_DETECTED',qrValue:'another-qr',at:101}),v)
 const type=success?'VALIDATION_APPROVED':'VALIDATION_REJECTED',result=success?approval:rejection
 assert.equal(reduce(v,{type,cycle:v.cycle-1,result,at:500}),v)
 const r=reduce(v,{type,cycle:v.cycle,result,at:500});assert.equal(r.state,success?'APPROVED':'REJECTED')
 assert.equal(r.cameraAttached,true);assert.equal(reduce(r,{type:'QR_DETECTED',qrValue:'other',at:501}),r)
 const resumed=reduce(r,{type:'RESULT_TIMEOUT',cycle:r.cycle})
 assert.equal(resumed.state,'SCANNING');assert.equal(resumed.validationResult,null);assert.equal(resumed.isProcessingScan,false)
 assert.equal(mayScan(resumed,'different-member',501),true)
 assert.equal(mayScan(resumed,'opaque-qr',999999),false,'Stationary QR is blocked even after cooldown')
 const absent=reduce(resumed,{type:'FRAME_OBSERVED',value:null,at:5000})
 const removed=reduce(absent,{type:'FRAME_OBSERVED',value:null,at:5600})
 assert.equal(mayScan(removed,'opaque-qr',5600),true)
})
test('decode misses and recent identical scans cannot evade cooldown/removal',()=>{
 let c={...scanning(),lastScannedValue:'qr',lastScanTimestamp:100,awaitingRemoval:true}
 c=reduce(c,{type:'FRAME_OBSERVED',value:null,at:500})
 c=reduce(c,{type:'FRAME_OBSERVED',value:'qr',at:700});assert.equal(c.absentSince,null)
 c=reduce(c,{type:'FRAME_OBSERVED',value:'different',at:701});assert.equal(c.awaitingRemoval,false)
 assert.equal(mayScan(c,'qr',1000),false);assert.equal(mayScan(c,'qr',2600),true)
})
test('technical errors return to scanning, never rejection; no automatic request storm',()=>{
 const v=reduce(scanning(),{type:'QR_DETECTED',qrValue:'qr',at:1})
 const c=reduce(v,{type:'VALIDATION_ERROR',cycle:v.cycle,error:{kind:'verification',message:'Unable to verify'},at:100})
 assert.equal(c.state,'SCANNING');assert.equal(c.validationResult,null);assert.equal(c.isProcessingScan,false)
 assert.equal(mayScan(c,'other',3000),false,'Show temporary error before next request')
 const clear=reduce(c,{type:'CLEAR_VERIFICATION_ERROR',cycle:c.cycle})
 assert.equal(mayScan(clear,'other',3000),true);assert.equal(mayScan(clear,'qr',3000),false)
})
test('camera failure/revocation invalidates stale result and timer events',()=>{
 for(const event of ['CAMERA_FAILED','CAMERA_PERMISSION_DENIED']){
  const v=reduce(scanning(),{type:'QR_DETECTED',qrValue:'qr',at:1})
  const c=reduce(v,{type:event,error:{kind:'camera',message:'Camera lost'}})
  assert.equal(c.cameraAttached,false);assert.equal(c.isProcessingScan,false)
  assert.equal(reduce(c,{type:'VALIDATION_APPROVED',cycle:v.cycle,result:approval,at:100}),c)
  assert.equal(reduce(c,{type:'RESULT_TIMEOUT',cycle:v.cycle}),c)
  const ready=reduce(c,{type:'CAMERA_PERMISSION_GRANTED'});assert.equal(ready.state,'CAMERA_READY')
  assert.equal(reduce(ready,{type:'CAMERA_INITIALIZED'}).state,'SCANNING')
 }
})
test('manual token fallback still validates when camera is unavailable',()=>{
 const v=reduce(initial,{type:'MANUAL_QR',qrValue:'manual',at:100})
 assert.equal(v.state,'VALIDATING');assert.equal(v.cameraAttached,false)
 const approved=reduce(v,{type:'VALIDATION_APPROVED',cycle:v.cycle,result:approval,at:500})
 assert.equal(reduce(approved,{type:'RESULT_TIMEOUT',cycle:v.cycle}).state,'PERMISSION_REQUIRED')
 const unmounted=reduce(approved,{type:'SCANNER_UNMOUNTED'})
 assert.equal(unmounted.lastScannedValue,null);assert.equal(unmounted.validationResult,null)
})
test('HTTP success alone is never approval',()=>{
 for(const raw of [null,{}, {success:true}, {...approval,status:'VALID'}, {...approval,checkin_time:'invalid'}, {...approval,customer_name:null}, {success:false,status:'SERVER_ERROR',message:'db failure'}])assert.equal(normalizeCheckIn(raw),null)
 assert.deepEqual(normalizeCheckIn(approval),approval)
})
for(const code of ['INVALID_QR','QR_EXPIRED','QR_ALREADY_USED','MEMBERSHIP_EXPIRED','MEMBERSHIP_PAUSED','DAILY_ACCESS_ALREADY_CONSUMED','WRONG_GYM','GYM_NOT_ELIGIBLE'])test(`business rejection ${code} is sanitized`,()=>{
 const r=normalizeCheckIn({success:false,status:code,message:'SQL traceback <script>private</script>'})
 assert.equal(r.success,false);assert.equal(r.status,code);assert.doesNotMatch(r.message,/SQL|script|private/)
})
test('legacy endpoint rejection messages preserve known paused/used/eligibility reasons',()=>{
 assert.match(normalizeCheckIn({success:false,status:'INVALID_QR',message:'This visit has been paused.'}).message,/paused/)
 assert.match(normalizeCheckIn({success:false,status:'QR_ALREADY_USED',message:"Today's gym access has already been used."}).message,/Today/)
 assert.match(normalizeCheckIn({success:false,status:'INVALID_QR',message:"{'code': 'GYM_NOT_ELIGIBLE'}"}).message,/not valid at this gym/)
})