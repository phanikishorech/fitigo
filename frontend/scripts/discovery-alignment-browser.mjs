// Layout regression using isolated storage and mocked APIs; no real map/key requests.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://127.0.0.1:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0
const pending = new Map(), errors = []
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence, timer = setTimeout(() => reject(Error(method)), 15000)
    pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (response.exceptionDetails) throw Error(response.exceptionDetails.exception?.description)
  return response.result.value
}
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params, path = new URL(request.url).pathname
  let body = [], status = 200
  if (path.endsWith('/gyms/discover')) body = { gyms: [], total_count: 0, page: 1, page_size: 8, has_more: false }
  else if (path.includes('/auth/') || path.endsWith('/users/me')) { body = { detail: 'Not authenticated' }; status = 401 }
  await command('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') }).catch(() => {})
}
try {
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/v1/*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: "localStorage.clear();Object.defineProperty(navigator,'geolocation',{value:undefined,configurable:true})" })
  for (const page of ['/home', '/explore']) {
    await command('Page.navigate', { url: origin + page })
    let ready = false
    for (let i = 0; i < 150; i++) {
      if (await evaluate("!!document.querySelector('.fg-map-controls select')")) { ready = true; break }
      await new Promise(resolve => setTimeout(resolve, 80))
    }
    assert.ok(ready, `${page} loaded`)
    for (const width of [320, 360, 390, 640, 768, 1024, 1440]) {
      await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width <= 640 })
      const layout = await evaluate(`(() => {
        const toolbar=document.querySelector('.fg-map-controls');
        const boxes=Array.from(toolbar.querySelectorAll('.fg-button,select')).map(el=>{const r=el.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,height:r.height,scroll:el.scrollHeight,client:el.clientHeight}});
        return {boxes,overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+1};
      })()`)
      assert.equal(layout.overflow, false, `${page} overflow at ${width}`)
      assert.equal(layout.boxes.length, 5)
      for (const box of layout.boxes) {
        assert.ok(Math.abs(box.height - 46) < 1, `control height at ${width}`)
        assert.ok(box.scroll <= box.client + 1, `control text fits at ${width}`)
      }
      const [map, list, radius, change, current] = layout.boxes
      assert.ok(Math.abs(map.bottom - list.bottom) < 1)
      if (width >= 768) assert.ok(layout.boxes.every(box => Math.abs(box.bottom - radius.bottom) < 1), `desktop baseline at ${width}`)
      else if (width <= 640) {
        assert.ok(radius.top >= map.bottom + 11)
        assert.ok(change.top >= radius.bottom + 11)
        assert.ok(Math.abs(change.bottom - current.bottom) < 1)
        assert.ok(change.right <= current.left)
      }
    }
  }
  assert.deepEqual(errors, [])
  console.log('PASS Home/Explore controls: aligned desktop baseline, equal 46px heights, orderly mobile rows, no overflow or clipped text at 320/360/390/640/768/1024/1440px.')
} finally {
  await command('Fetch.disable').catch(() => {})
  for (const item of pending.values()) clearTimeout(item.timer)
  ws.close(); await target.dispose()
}