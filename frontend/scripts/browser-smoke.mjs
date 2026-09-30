// Public browser smoke checks using native Node WebSocket + Chrome CDP.
// Optional FITIGO_TEST_EMAIL/PASSWORD enables real login; never prints credentials or tokens.
// Start an isolated headless Chrome with --remote-debugging-port=9229 first.
import assert from 'node:assert/strict'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const tabs = await (await fetch('http://localhost:9229/json')).json()
const target = tabs.find(tab => tab.type === 'page')
if (!target) throw new Error('No isolated browser page found.')
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
let sequence = 0
const pending = new Map()
const exceptions = []
ws.onmessage = event => {
  const message = JSON.parse(event.data)
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text)
  if (message.id) {
    const handler = pending.get(message.id)
    if (handler) { clearTimeout(handler.timer); pending.delete(message.id); message.error ? handler.reject(new Error(message.error.message)) : handler.resolve(message.result) }
  }
}
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`Timed out: ${method}`)) }, 15000)
    pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params }))
  })
}
const evaluate = async expression => (await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })).result.value
async function waitFor(expression) {
  for (let attempt = 0; attempt < 80; attempt++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 150)) }
  throw new Error(`Page did not become ready: ${expression}`)
}
async function visit(path, text) {
  await command('Page.navigate', { url: `http://localhost:5173${path}` })
  await waitFor(`document.body.innerText.includes(${JSON.stringify(text)})`)
  await waitFor(`!document.querySelector('[aria-label="Loading"]')`)
}
async function checkWidth(width) {
  await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 600 })
  await new Promise(resolve => setTimeout(resolve, 150))
  const sizes = await evaluate('({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})')
  assert.ok(sizes.scroll <= sizes.client + 1, `Horizontal overflow at ${width}: ${JSON.stringify(sizes)}`)
}
try {
  await command('Runtime.enable'); await command('Page.enable')
  await visit('/home', 'Your next workout.')
  assert.ok(await evaluate('document.querySelectorAll(".fg-gym-card").length > 0'), 'Home has live gym cards')
  for (const width of [360, 390, 430, 768, 1024, 1280, 1440]) { await checkWidth(width); console.log(`PASS home layout ${width}px`) }
  let screenshot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile(join(tmpdir(), 'fitigo-home-desktop.png'), Buffer.from(screenshot.data, 'base64'))
  await checkWidth(390)
  screenshot = await command('Page.captureScreenshot', { format: 'png' })
  await writeFile(join(tmpdir(), 'fitigo-home-mobile.png'), Buffer.from(screenshot.data, 'base64'))
  await evaluate(`document.querySelector('.fg-header-actions button').click()`)
  await waitFor(`!!document.querySelector('[role="dialog"]')`)
  await checkWidth(360)
  assert.equal(await evaluate(`document.querySelector('[role="dialog"]').innerText.includes('Google')`), false)
  await evaluate(`Array.from(document.querySelectorAll('[aria-label="Sign-in method"] button')).find(b=>b.textContent==='Password').click()`)
  await waitFor(`!!document.querySelector('form[aria-label="Password sign in"]')`)
  await checkWidth(360)
  assert.equal(await evaluate(`document.querySelector('form[aria-label="Password sign in"] button[type="submit"]').disabled`), true)
  assert.equal(await evaluate(`document.querySelector('input[name="password"]').type`), 'password')
  await evaluate(`document.querySelector('[aria-label="Show password"]').click()`)
  assert.equal(await evaluate(`document.querySelector('input[name="password"]').type`), 'text')
  await evaluate(`document.querySelector('[aria-label="Hide password"]').click()`)
  await evaluate(`Array.from(document.querySelectorAll('[aria-label="Sign-in method"] button')).find(b=>b.textContent==='OTP').click()`)
  await waitFor(`!!document.querySelector('[aria-label="Switch to mobile OTP login"]')`)
  await evaluate(`document.querySelector('[aria-label="Switch to mobile OTP login"]').click()`)
  await waitFor(`!!document.querySelector('[aria-label="Mobile number"]')`)
  console.log('PASS OTP/password switching, password visibility, mobile OTP, and empty form validation')
  await evaluate(`document.querySelector('[aria-label="Close authentication modal"]').click()`)
  console.log('PASS login dialog opens without unsupported OAuth')
  await visit('/explore', 'Explore gyms'); await checkWidth(390)
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Filters')).click()`)
  await waitFor(`!!document.querySelector('dialog[open]')`)
  await checkWidth(360)
  await evaluate(`document.querySelector('[aria-label="Close dialog"]').click()`)
  console.log('PASS discovery and filter sheet')
  await visit('/gyms/188', 'FitZone Premium Gym'); await checkWidth(390); await checkWidth(1440)
  console.log('PASS gym detail mobile and desktop')
  await visit('/gyms/188/book/access', 'How do you want to work out?')
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Continue')).click()`)
  await waitFor(`document.body.innerText.includes('Make time for yourself')`)
  await waitFor(`!document.querySelector('[aria-label="Loading"]')`)
  await checkWidth(360)
  console.log('PASS access-to-schedule navigation')
  for (const path of ['/cart', '/checkout', '/wallet', '/bookings', '/profile', '/access/qr', '/membership/checkout?gymId=188&planId=1']) {
    await visit(path, 'Sign in to continue'); await checkWidth(390); console.log(`PASS protected ${path}`)
  }
  await visit('/auth/login?returnTo=%2Fcart', 'Welcome to FitiGo')
  await waitFor(`!!document.querySelector('[role="dialog"]')`)
  console.log('PASS direct login route opens OTP login')
  if (process.env.FITIGO_TEST_EMAIL && process.env.FITIGO_TEST_PASSWORD) {
    await evaluate(`Array.from(document.querySelectorAll('[aria-label="Sign-in method"] button')).find(b=>b.textContent==='Password').click()`)
    await waitFor(`!!document.querySelector('input[name="password"]')`)
    const fill = async (name, value) => evaluate(`(() => { const input=document.querySelector('input[name=${JSON.stringify(name)}]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,${JSON.stringify(value)}); input.dispatchEvent(new Event('input',{bubbles:true})); })()`)
    await fill('email', process.env.FITIGO_TEST_EMAIL)
    await fill('password', 'intentionally-incorrect-browser-test-password')
    await evaluate(`document.querySelector('form[aria-label="Password sign in"]').requestSubmit()`)
    await waitFor(`document.body.innerText.includes('The email or password is incorrect.')`)
    console.log('PASS invalid password has a readable error and permits retry')
    await fill('password', process.env.FITIGO_TEST_PASSWORD)
    await evaluate(`document.querySelector('form[aria-label="Password sign in"]').requestSubmit()`)
    await waitFor(`location.pathname === '/cart' && !document.querySelector('[role="dialog"]')`)
    await waitFor(`document.body.innerText.includes('Your cart')`)
    console.log('PASS real password login and return to intended cart route')
    await evaluate(`import('/src/auth.ts').then(auth => auth.clearTokens())`)
  }
  await visit('/not-a-route', 'This page took a wrong turn')
  assert.deepEqual(exceptions, [], 'No uncaught browser exceptions')
  console.log('PASS not-found screen; no uncaught exceptions')
  console.log(`Screenshots saved in ${tmpdir()}`)
} finally { ws.close() }