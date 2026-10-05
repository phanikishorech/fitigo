// Isolated camera/API fixtures. Uses real video playback and real jsQR decoding.
// No live credentials, QR entitlements, or check-ins are used.
import assert from 'node:assert/strict'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const endpoint = 'http://localhost:9231'
const target = await (await fetch(`${endpoint}/json/new?${encodeURIComponent(origin)}`, { method: 'PUT' })).json()
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0
const pending = new Map(), failures = [], exceptions = [], calls = []
let status = 'VALID'
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; const timer = setTimeout(() => reject(new Error(`Timeout: ${method}`)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const r = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(100) } throw new Error(`Not ready: ${expression}\n${await evaluate('document.body.innerText')}`) }
async function click(text) { await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(text)}).click()`); await wait(80) }
ws.onmessage = async event => {
  const message = JSON.parse(event.data)
  if (pending.has(message.id)) { const p = pending.get(message.id); clearTimeout(p.timer); pending.delete(message.id); message.error ? p.reject(new Error(message.error.message)) : p.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text)
  if (message.method === 'Fetch.requestPaused') {
    const { requestId, request } = message.params
    try {
      const path = new URL(request.url).pathname
      let body
      if (path.endsWith('/users/me')) body = { id: 9001, first_name: 'Scanner', last_name: 'Test', email: 'scanner@example.test', phone: null }
      else if (path.endsWith('/users/me/roles')) body = ['GYM_STAFF']
      else if (path.endsWith('/gym-staff/gyms')) body = [{ id: 19, name: 'Scanner Fixture Gym', city: 'Test City' }]
      else if (path.endsWith('/checkins/validate')) {
        assert.equal(request.method, 'POST'); calls.push(JSON.parse(request.postData))
        assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`), true, 'Camera stops before validation')
        await wait(400)
        body = status === 'VALID' ? { success: true, status: 'VALID', customer_name: 'Fixture Member', gym_name: 'Scanner Fixture Gym', access_type: 'MULTI_GYM', checkin_time: new Date().toISOString() } : { success: false, status, message: status === 'QR_EXPIRED' ? 'QR expired' : status === 'QR_ALREADY_USED' ? 'QR already used' : 'Invalid QR' }
      } else throw new Error(`Unexpected API ${path}`)
      await command('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
    } catch (error) { failures.push(error.message); await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }) }
  }
}
try {
  await command('Runtime.enable'); await command('Page.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.setItem('fitigo:access_token','isolated-scanner-fixture');
    Object.defineProperty(window,'BarcodeDetector',{value:undefined,configurable:true});
    window.testStreams=[]; window.testMode='blank'; window.testCameraError=''; window.testDelay=0; window.testRequests=0;
    navigator.mediaDevices.getUserMedia=async constraints=>{
      window.testRequests++; window.testConstraints=constraints;
      if(window.testCameraError) throw new DOMException('Fixture error',window.testCameraError);
      const canvas=document.createElement('canvas');canvas.width=canvas.height=410;
      const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,410,410);
      window.testCanvas=canvas;
      if(window.testMode==='qr') {
        const {accessQrMatrix}=await import('/src/components/accessQrMatrix.ts');
        ctx.fillStyle='black';accessQrMatrix('GYMACCESS:scanner-fixture-not-valid').forEach((row,y)=>row.forEach((dark,x)=>{if(dark)ctx.fillRect((x+4)*10,(y+4)*10,10,10)}));
      }
      const stream=canvas.captureStream(10);window.testStreams.push(stream);
      const tick=setInterval(()=>{ctx.drawImage(canvas,0,0);if(stream.getTracks().every(t=>t.readyState==='ended'))clearInterval(tick)},80);
      if(window.testDelay)await new Promise(r=>setTimeout(r,window.testDelay));
      return stream;
    };
  ` })
  async function reset() { await command('Page.navigate', { url: `${origin}/owner/check-in` }); await until(`document.body.innerText.includes('Start camera')`) }
  await reset()
  assert.equal(await evaluate('typeof BarcodeDetector'), 'undefined')
  await click('Start camera'); await until(`document.querySelector('video')?.videoWidth>0 && document.body.innerText.includes('Stop camera')`)
  assert.equal(await evaluate('window.testConstraints.video.facingMode.ideal'), 'environment')
  await wait(800); assert.equal(calls.length, 0, 'Blank frames do not submit')
  await click('Stop camera'); assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`), true)
  console.log('PASS existing Start/Stop buttons, live preview, blank frames, rear camera preference, cleanup; BarcodeDetector absent')
  for (const next of ['VALID', 'QR_EXPIRED', 'QR_ALREADY_USED', 'INVALID_QR']) {
    await reset(); status = next; await evaluate(`window.testMode='qr'`)
    const before = calls.length
    await click('Start camera'); await until(`document.body.innerText.includes(${JSON.stringify(next === 'VALID' ? 'Check-in successful' : 'Access denied')})`)
    await wait(900); assert.equal(calls.length, before + 1)
    assert.deepEqual(calls.at(-1), { gym_id: 19, qr_token: 'GYMACCESS:scanner-fixture-not-valid' })
    assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`), true)
  }
  console.log('PASS real QR decoding → unchanged check-in API; valid/expired/used/invalid results; one submission per scan')
  for (const [error, text] of [['NotAllowedError','Camera permission was denied'],['NotFoundError','No usable camera'],['NotReadableError','camera is busy']]) {
    await reset(); await evaluate(`window.testCameraError=${JSON.stringify(error)}`); await click('Start camera'); await until(`document.body.innerText.includes(${JSON.stringify(text)})`)
  }
  console.log('PASS permission denied, missing camera, busy camera')
  await reset(); await evaluate(`HTMLCanvasElement.prototype.getContext=()=>null`); await click('Start camera'); await until(`document.body.innerText.includes('Unable to initialize QR scanning')`)
  assert.equal(await evaluate('window.testRequests'), 0)
  await reset(); await evaluate(`window.testDelay=500;const button=Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()==='Start camera');button.click();button.click()`)
  await until(`document.body.innerText.includes('Stop camera')`); assert.equal(await evaluate('window.testRequests'),1)
  await evaluate(`Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'))`)
  assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`),true)
  console.log('PASS initialization failure, duplicate start prevention, hidden-page cleanup')
  await reset(); await click('Start camera'); await until(`document.body.innerText.includes('Stop camera')`)
  await evaluate(`document.querySelector('a[href="/owner/settings"]').click()`)
  await until(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`)
  await reset(); await evaluate(`window.testDelay=1000`); await click('Start camera'); await until('window.testStreams.length===1')
  await evaluate(`document.querySelector('a[href="/owner/settings"]').click()`); await wait(1300)
  assert.equal(await evaluate(`window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==='ended'))`), true)
  console.log('PASS unmount cleanup during playback and delayed camera initialization')
  await reset(); status='VALID'
  await evaluate(`document.querySelector('details').open=true;const el=document.querySelector('details input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'manual-fixture');el.dispatchEvent(new Event('input',{bubbles:true}))`)
  await wait(100); await evaluate(`document.querySelector('details form').requestSubmit()`)
  await until(`document.body.innerText.includes('Check-in successful')`)
  assert.deepEqual(calls.at(-1), { gym_id:19, qr_token:'manual-fixture' })
  assert.equal(await evaluate('window.testRequests'), 0)
  assert.deepEqual(failures, []); assert.deepEqual(exceptions, [])
  console.log('PASS manual token unchanged; no unexpected requests or runtime exceptions')
} finally {
  await command('Fetch.disable').catch(()=>{})
  ws.close(); await fetch(`${endpoint}/json/close/${target.id}`)
}