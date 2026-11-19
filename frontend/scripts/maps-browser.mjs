// Isolated Chrome context, mocked APIs/geolocation/Maps. No Google requests or real data writes.
import assert from 'node:assert/strict'
import { isolatedBrowserTarget } from './isolated-browser.mjs'
const origin = process.env.FITIGO_TEST_ORIGIN || 'http://127.0.0.1:5173'
const target = await isolatedBrowserTarget(), ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0, apiError = false, empty = false, missing = false, mode = 'granted', mapsFail = false
const pending = new Map(), errors = [], requests = [], external = []
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; const timer = setTimeout(() => reject(Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
async function evaluate(expression) { const response = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (response.exceptionDetails) throw Error(JSON.stringify(response.exceptionDetails)); return response.result.value }
async function until(expression) { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 70)) } throw Error(JSON.stringify({ expression, body: await evaluate('document.body.innerText'), errors })) }
async function click(text, selector = 'button') { await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)})).find(el => el.textContent.trim() === ${JSON.stringify(text)}).click()`) }
const gym = { gym_id: 1, gym_name: 'Map fixture gym', latitude: '12.01', longitude: '77.01', address: 'Test-only street', locality: 'Fixture area', city: 'Fixture city', distance_km: 1.5, average_rating: 4.5, review_count: 2, starting_price: '100', facilities: [], is_featured: false }
const details = { ...gym, location: { latitude: 12.01, longitude: 77.01, full_address: 'Test-only street' }, images: [], ratings: { average_rating: 4.5, review_count: 2 }, opening_hours: { weekly: [], open_now: true }, description: 'Test fixture', important_information: [], rules: [], amenities: [], classes_nearby: [], reviews: [], membership_access: { status: 'NO_ACTIVE_MEMBERSHIP', day_pass_price: '100' } }
ws.onmessage = async event => {
  const message = JSON.parse(event.data), item = pending.get(message.id)
  if (item) { pending.delete(message.id); clearTimeout(item.timer); message.error ? item.reject(Error(message.error.message)) : item.resolve(message.result) }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text)
  if (message.method !== 'Fetch.requestPaused') return
  const { requestId, request } = message.params, url = new URL(request.url)
  let body = {}, status = 200
  if (url.hostname === 'maps.googleapis.com' || url.hostname.endsWith('.gstatic.com')) { await command('Fetch.failRequest', { requestId, errorReason: 'Failed' }); return }
  if (url.hostname === 'www.google.com') { external.push(url.href); await command('Fetch.failRequest', { requestId, errorReason: 'Aborted' }); return }
  if (url.pathname.endsWith('/gyms/discover')) { requests.push(url.searchParams.toString()); body = apiError ? { detail: 'Fixture discovery failure' } : { gyms: empty ? [] : [gym], total_count: empty ? 0 : 1, page: 1, page_size: 8, has_more: false }; status = apiError ? 503 : 200 }
  else if (url.pathname.endsWith('/gyms/1/details')) body = { ...details, location: missing ? { full_address: 'Test-only street' } : details.location }
  else if (url.pathname.endsWith('/meta/locations')) body = [{ location_name: 'Fixture north', latitude: 13, longitude: 78, gym_count: 1 }, { location_name: 'Fixture south', latitude: 14, longitude: 79, gym_count: 1 }]
  else if (url.pathname.endsWith('/meta/gym-types')) body = ['All Gym Types']
  else if (url.pathname.endsWith('/facilities')) body = []
  else if (url.pathname.includes('/auth/session') || url.pathname.endsWith('/users/me')) { status = 401; body = { detail: 'Not authenticated' } }
  else body = []
  await command('Fetch.fulfillRequest', { requestId, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(body)).toString('base64') })
}
function bootstrap() {
  const respond = mode === 'unavailable' ? 'fail({code:2})' : 'ok({coords:{latitude:12,longitude:77,accuracy:25},timestamp:Date.now()})'
  return `
    window.__geoCalls=0;window.__mapBuilds=0;window.__fitCount=0;window.__routes=[];window.__markers=[];
    const status={state:${JSON.stringify(mode === 'denied' ? 'denied' : 'granted')},addEventListener:(name,fn)=>window.__revoke=()=>{status.state='denied';fn()}};
    Object.defineProperty(navigator,'permissions',{value:{query:async()=>status},configurable:true});
    Object.defineProperty(navigator,'geolocation',{value:{getCurrentPosition:(ok,fail)=>{window.__geoCalls++;queueMicrotask(()=>{${respond}})}},configurable:true});
    class Bounds{extend(){return this}}
    class MapMock{constructor(el,options){window.__mapBuilds++;this.el=el;this.zoom=options.zoom;this.events={};el.textContent='Mock Google map';}addListener(name,fn){this.events[name]=fn;if(name==='idle')setTimeout(()=>fn({}),0);return{remove:()=>delete this.events[name]}}fitBounds(){window.__fitCount++}getZoom(){return this.zoom}setZoom(z){this.zoom=z;this.events.zoom_changed?.({})}setCenter(){}}
    class Marker{constructor(options){this.options=options;this.node=document.createElement('button');this.node.textContent=options.title;this.node.setAttribute('data-map-marker','');this.node.onclick=()=>this.click?.({});this.map=options.map;window.__markers.push(this)}set map(value){this._map=value;if(value)value.el.append(this.node);else this.node.remove()}get map(){return this._map}addListener(name,fn){this.click=fn;return{remove:()=>{this.click=null}}}}
    class Overlay{setMap(){}}
    const computeRoutes=async request=>{window.__routes.push(request);return{routes:[{distanceMeters:2500,durationMillis:600000,viewport:new Bounds(),warnings:['Test-only route warning'],createPolylines:()=>[new Overlay()]}]}};
    window.google={maps:{Map:MapMock,LatLngBounds:Bounds,Circle:Overlay,marker:{AdvancedMarkerElement:Marker},importLibrary:async()=>({}),routes:{Route:{computeRoutes}}}};
    ${mapsFail ? 'delete window.google;' : ''}
  `
}
let bootstrapId
async function page(path, text) {
  if (bootstrapId) await command('Page.removeScriptToEvaluateOnNewDocument', { identifier: bootstrapId })
  bootstrapId = (await command('Page.addScriptToEvaluateOnNewDocument', { source: bootstrap() })).identifier
  await command('Page.navigate', { url: origin + path }); await until(`document.body?.innerText.includes(${JSON.stringify(text)})`)
}
try {
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*/api/*' }, { urlPattern: 'https://www.google.com/*' }, { urlPattern: 'https://maps.googleapis.com/*' }, { urlPattern: '*://*.gstatic.com/*' }] })
  await page('/home', 'Mock Google map')
  assert.equal(await evaluate('window.__geoCalls'), 1)
  assert.equal(await evaluate("localStorage.getItem('fitigo.location')"), null)
  for (const radius of [5, 10, 20, 50]) {
    await evaluate(`var select=document.querySelector('[aria-label="Search radius"]');select.value='${radius}';select.dispatchEvent(new Event('change',{bubbles:true}))`)
    await until(`document.querySelector('[aria-label="Search radius"]').value==='${radius}' && document.body.innerText.includes('Mock Google map')`)
    assert.ok(requests.some(value => new URLSearchParams(value).get('radius_km') === String(radius)))
  }
  const fits = await evaluate('window.__fitCount')
  await click('Map fixture gym', '[data-map-marker]'); await until("document.body.innerText.includes('View Gym Details')")
  assert.equal(await evaluate('window.__fitCount'), fits)
  await click('List View'); await until("!!document.querySelector('.fg-gym-card')")
  assert.equal(await evaluate("document.querySelector('[aria-label=\"Search radius\"]').value"), '50')
  await click('Map View'); await until("document.body.innerText.includes('Mock Google map')")
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true) }
  await click('Map fixture gym', '[data-map-marker]'); await click('View Gym Details', 'a'); await until("document.body.innerText.includes('Get Directions')")
  assert.ok(await evaluate("document.body.innerText.includes('Book a Visit') && document.body.innerText.includes('View Membership Plans')"))
  assert.equal(await evaluate("!!document.querySelector('.fg-map-route')"), false)
  assert.equal(await evaluate("!!Array.from(document.querySelectorAll('aside a')).find(a=>a.textContent==='Get Directions')"), true)
  for (const width of [360, 768, 1440]) { await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 640 }); assert.equal(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1'), true) }
  mode = 'denied'; mapsFail = true; await page('/gyms/1', 'Get Directions')
  assert.equal(await evaluate('window.__geoCalls'), 0)
  assert.equal(await evaluate('window.__mapBuilds'), 0)
  assert.equal(await evaluate("new URL(Array.from(document.querySelectorAll('a')).find(a=>a.textContent==='Get Directions').href).searchParams.get('destination')"), '12.01,77.01')
  await click('Get Directions', 'a')
  for (let i = 0; i < 100 && !external.length; i++) await new Promise(resolve => setTimeout(resolve, 50))
  assert.ok(external.length); assert.equal(new URL(external.at(-1)).searchParams.has('origin'), false)
  mapsFail = false
  await page('/home', 'Choose an area'); assert.equal(await evaluate('window.__geoCalls'), 0)
  await page('/location', 'Fixture north'); await click('Fixture north1 gyms', '.fg-list-row').catch(async () => { await evaluate("document.querySelector('.fg-list-row').click()") })
  await until("document.body.innerText.includes('Mock Google map')")
  assert.ok(requests.some(value => new URLSearchParams(value).get('latitude') === '13'))
  await page('/location', 'Fixture south'); await evaluate("document.querySelectorAll('.fg-list-row')[1].click()")
  await until("document.body.innerText.includes('Mock Google map')")
  assert.ok(requests.some(value => new URLSearchParams(value).get('latitude') === '14'))
  empty = true; await page('/home', 'No FitiGo gyms nearby'); empty = false
  apiError = true; await page('/home', 'Something went wrong'); apiError = false; await click('Try again'); await until("document.body.innerText.includes('Mock Google map')")
  missing = true; await page('/gyms/1', 'Location unavailable'); missing = false
  mapsFail = true; await page('/home', 'Map View'); await until("/Interactive maps are not configured|Google Maps could not load/.test(document.body.innerText)"); await click('List View'); await until("!!document.querySelector('.fg-gym-card')"); mapsFail = false
  await evaluate('localStorage.clear()'); mode = 'unavailable'; await page('/home', 'Your location is unavailable')
  assert.equal(errors.length, 0, JSON.stringify(errors))
  console.log('PASS: mocked geolocation, four radii, marker/details, map/list, three viewports, sidebar-only directions without Maps configuration or permission, external URL, manual areas, empty/error/retry, missing coordinates and Maps failure.')
} finally { ws.close(); await target.dispose() }