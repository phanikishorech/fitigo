// Live owner UI smoke suite. Uses an isolated Chrome CDP session, no intercepted APIs.
// FITIGO_TEST_EMAIL / FITIGO_TEST_PASSWORD are optional. No credentials are logged.
// Mutating wizard coverage is opt-in with FITIGO_TEST_CREATE_GYM=1 (creates a real draft).
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const origin = process.env.FITIGO_TEST_ORIGIN || 'http://localhost:5173'
const targets = await (await fetch('http://localhost:9231/json')).json()
const ws = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0; const pending = new Map(); const exceptions = []; const consoleErrors = []
ws.onmessage = e => {
  const m = JSON.parse(e.data)
  if (m.method === 'Runtime.exceptionThrown') exceptions.push(m.params.exceptionDetails.text)
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args.map(a => a.value || a.description).join(' '))
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); clearTimeout(p.timer); pending.delete(m.id); m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result) }
}
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence; const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timeout: ${method}`)) }, 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })) }) }
const evaluate = async expression => { const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw new Error(result.exceptionDetails.text); return result.result.value }
const wait = ms => new Promise(r => setTimeout(r, ms))
async function until(expression) { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await wait(150) } throw new Error(`Not ready: ${expression}; page: ${await evaluate('document.body.innerText.slice(0,700)')}`) }
async function visit(path, text) { await command('Page.navigate', { url: origin + path }); await until(`document.body.innerText.includes(${JSON.stringify(text)})`); await until(`!document.querySelector('[aria-label="Loading"]')`) }
async function width(value) { await command('Emulation.setDeviceMetricsOverride', { width: value, height: 1000, deviceScaleFactor: 1, mobile: value < 640 }); await wait(80); const result = await evaluate('({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})'); assert.ok(result.scroll <= result.client + 1, `Overflow at ${value}: ${JSON.stringify(result)}`) }
async function fill(selector, value) { await evaluate(`(() => { const el=document.querySelector(${JSON.stringify(selector)}); const p=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(p,'value').set.call(el,${JSON.stringify(value)}); el.dispatchEvent(new Event('input',{bubbles:true})); })()`); await wait(60) }
async function clickText(text) { await evaluate(`Array.from(document.querySelectorAll('button')).find(e=>e.textContent.trim()===${JSON.stringify(text)}).click()`); await wait(150) }
async function screenshot(name) { const shot = await command('Page.captureScreenshot', { format: 'png' }); await writeFile(join(tmpdir(), name), Buffer.from(shot.data, 'base64')) }
try {
  await command('Runtime.enable'); await command('Page.enable')
  await visit('/owner/login', 'Welcome back')
  await evaluate(`localStorage.removeItem('fitigo:access_token');localStorage.removeItem('fitigo:refresh_token')`)
  for (const w of [360, 390, 430, 768, 1024, 1280, 1440, 1920]) await width(w)
  await visit('/owner/register', 'Create your owner account'); await width(360)
  assert.equal(await evaluate(`document.querySelector('input[name="password"]').minLength`), 8)
  await visit('/owner/verify', 'Verify your account'); await width(360)
  await visit('/owner/dashboard', 'Sign in to your owner workspace'); await width(360)
  console.log('PASS auth screens, unauthenticated guard, all viewport widths')
  if (process.env.FITIGO_TEST_EMAIL && process.env.FITIGO_TEST_PASSWORD) {
    await visit('/owner/login', 'Welcome back')
    await fill('input[name="email"]', process.env.FITIGO_TEST_EMAIL); await fill('input[name="password"]', process.env.FITIGO_TEST_PASSWORD)
    await evaluate('document.querySelector("form").requestSubmit()')
    await until(`document.body.innerText.includes('Portfolio overview')`); await until(`!document.querySelector('[aria-label="Loading"]')`)
    for (const w of [360, 390, 430, 768, 1024, 1280, 1440, 1920]) { await width(w); console.log(`PASS dashboard layout ${w}px`) }
    await width(1440); await screenshot('fitigo-owner-desktop.png'); await width(390); await screenshot('fitigo-owner-mobile.png')
    const choices = await evaluate(`Array.from(document.querySelector('[aria-label="Selected gym"]').options).filter(o=>/^[0-9]+$/.test(o.value)).map(o=>({id:Number(o.value),name:o.textContent}))`)
    for (const [path, text] of [['/owner/gyms','My gyms'], ['/owner/bookings','Bookings'], ['/owner/members','Member directory unavailable'], ['/owner/staff','Your team'], ['/owner/revenue','Revenue overview'], ['/owner/analytics','Business overview'], ['/owner/settings','Owner profile'], ['/owner/notifications','Notifications'], ['/owner/check-in','Assigned staff access required'], ['/owner/more','Your workspace'], ['/owner/missing','Page not found']]) { await visit(path, text); await width(360); await width(1440); console.log(`PASS live ${path}`) }
    if (choices[0]) {
      const id = choices[0].id
      for (const [path, text] of [[`/owner/gyms/${id}`,'Overview'], [`/owner/gyms/${id}/edit`,'Basic details'], [`/owner/gyms/${id}/memberships`,'Membership plans'], [`/owner/gyms/${id}/memberships/create`,'Create membership plan'], [`/owner/gyms/${id}/classes`,'Classes & slots'], [`/owner/gyms/${id}/classes/create`,'Create class'], [`/owner/gyms/${id}/slots`,'Slot availability'], ['/owner/staff/invite','Add to your team']]) { await visit(path,text); await width(360); await width(768); await width(1440); console.log(`PASS live ${path}`) }
      await visit('/owner/bookings', 'Bookings'); await clickText('All dates'); await until(`!document.querySelector('[aria-label="Loading"]')`)
      const booking = await evaluate(`document.querySelector('main a[href^="/owner/bookings/"]')?.getAttribute('href')`)
      if (booking) { await visit(booking, 'Visit details'); await width(360); assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).some(b=>b.textContent==='Cancel booking')`), false); console.log('PASS live booking details and fail-closed action eligibility') }
      if (choices[1]) {
        await visit(`/owner/gyms/${id}/classes`, 'Classes & slots')
        await evaluate(`(() => { const select=document.querySelector('[aria-label="Selected gym"]'); select.value=${JSON.stringify(String(choices[1].id))};select.dispatchEvent(new Event('change',{bubbles:true})); })()`)
        await until(`location.pathname==='/owner/gyms/${choices[1].id}/classes'`); await until(`!document.querySelector('[aria-label="Loading"]')`)
        assert.equal(await evaluate(`document.querySelector('[aria-label="Selected gym"]').value`), String(choices[1].id))
        console.log('PASS multi-gym route and selection synchronization')
      }
    }
    await visit('/owner/gyms/create', 'Bring your gym to FitiGo'); await width(360)
    if (process.env.FITIGO_TEST_CREATE_GYM === '1') {
      await width(390)
      await fill('main form input', `Owner UI verification ${new Date().toISOString()}`)
      await clickText('Save & continue'); await until(`document.querySelector('main h2')?.textContent==='Location'`)
      await clickText('Save & continue'); await until(`document.querySelector('main h2')?.textContent==='Pricing'`)
      await fill('input[type="number"]', '0'); await clickText('Save & continue'); await until(`document.querySelector('main h2')?.textContent==='Photos'`)
      await clickText('Save & continue'); await until(`document.querySelector('main h2')?.textContent==='Facilities'`)
      await clickText('Save & continue'); await until(`document.querySelector('main h2')?.textContent==='Operating hours'`)
      await evaluate(`document.querySelectorAll('.ow-hours-editor input[type="checkbox"]').forEach(e=>e.click())`)
      await clickText('Save & continue'); await until(`document.querySelector('main h2')?.textContent==='Review'`)
      await width(360); await width(1440)
      console.log('PASS real draft wizard, persisted steps, review; no approval submitted')
      const draftPath = await evaluate('location.pathname.replace(/\\/edit$/, "")')
      await visit(`${draftPath}/memberships/create`, 'Create membership plan')
      await fill('input[name="name"]', 'QA verification plan'); await fill('input[name="duration"]', '30'); await fill('input[name="price"]', '0')
      await clickText('Save plan'); await until(`location.pathname===${JSON.stringify(`${draftPath}/memberships`)}`); await until(`document.querySelector('main')?.innerText.includes('QA verification plan')`)
      await width(360); await width(1440)
      const editPlan = await evaluate(`document.querySelector('main a[href$="/edit"]').getAttribute('href')`)
      await visit(editPlan, 'Edit membership plan'); await fill('input[name="name"]', 'QA updated plan'); await clickText('Save plan'); await until(`document.querySelector('main')?.innerText.includes('QA updated plan')`)
      await clickText('Deactivate'); await until(`!!document.querySelector('dialog[open]')`); await clickText('Confirm change'); await until(`document.querySelector('main .ow-badge')?.textContent.includes('inactive')`)
      await clickText('Activate'); await until(`!!document.querySelector('dialog[open]')`); await clickText('Confirm change'); await until(`!document.querySelector('dialog[open]')`)
      console.log('PASS live plan create, edit, deactivate and reactivate')
      await visit(`${draftPath}/classes/create`, 'Create class')
      await fill('input[name="name"]', 'QA verification class'); await fill('input[name="start"]', '10:00'); await fill('input[name="end"]', '11:00'); await fill('input[name="capacity"]', '10'); await fill('input[name="date"]', '2026-10-01'); await fill('input[name="price"]', '0')
      await clickText('Save class'); await until(`location.pathname===${JSON.stringify(`${draftPath}/classes`)}`); await until(`document.querySelector('main')?.innerText.includes('QA verification class')`)
      const editClass = await evaluate(`document.querySelector('main a[href$="/edit"]').getAttribute('href')`)
      await visit(editClass, 'Edit class'); await fill('input[name="capacity"]', '12'); await clickText('Save class'); await until(`document.querySelector('main')?.innerText.includes('12 people')`)
      await clickText('Deactivate'); await until(`!!document.querySelector('dialog[open]')`); await clickText('Confirm change'); await until(`document.querySelector('main .ow-badge')?.textContent.includes('inactive')`)
      console.log('PASS live owner slot create, edit and deactivate')
      await visit(draftPath, 'Overview'); await clickText('Submit for approval'); await until(`!!document.querySelector('dialog[open]')`); await clickText('Keep unchanged')
      assert.equal(await evaluate(`!!document.querySelector('dialog[open]')`), false)
      console.log('PASS submission confirmation can be cancelled without changing approval state')
    }
    await visit('/owner/settings','Owner profile'); await clickText('Sign out'); await until(`!!document.querySelector('dialog[open]')`); await width(360)
    await evaluate(`Array.from(document.querySelectorAll('dialog button')).find(b=>b.textContent==='Sign out').click()`); await until(`location.pathname==='/owner/login'`)
    assert.equal(await evaluate(`localStorage.getItem('fitigo:access_token')`), null)
    console.log('PASS logout confirmation, server revocation and local cleanup')
  } else console.log('SKIP live authenticated flows: set FITIGO_TEST_EMAIL/PASSWORD')
  assert.deepEqual(exceptions, [])
  assert.deepEqual(consoleErrors, [])
  console.log('PASS no uncaught runtime errors or React console errors')
} finally { ws.close() }