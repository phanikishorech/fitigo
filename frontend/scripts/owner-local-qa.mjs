// Explicit local-only bootstrap. Creates a QA owner and two real DRAFT gyms.
// Does not approve gyms, send invitations, charge payments or modify existing users.
import { randomBytes } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

if (process.env.FITIGO_CREATE_LOCAL_QA !== '1') throw new Error('Set FITIGO_CREATE_LOCAL_QA=1 to create local QA records.')
const base = 'http://localhost:8000/api/v1'
const email = `owner-qa-${Date.now()}@example.com`
const password = randomBytes(24).toString('base64url')
async function post(path, body, token) {
  const res = await fetch(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(body), signal: AbortSignal.timeout(15000) })
  if (!res.ok) throw new Error(`QA request ${path} returned ${res.status}`)
  return res.json()
}
const user = await post('/auth/register/gym-owner', { first_name: 'Portal', last_name: 'QA', email, password })
const auth = await post('/auth/login', { email, password })
const gymIds = []
for (const name of ['Owner portal QA — draft A', 'Owner portal QA — draft B']) {
  const gym = await post('/gym-owner/gyms', { name, description: 'Local owner UI verification record. Not submitted for approval.', city: 'QA workspace', gym_price_per_person: '0.00' }, auth.access_token)
  gymIds.push(gym.id)
}
await post('/auth/logout', { refresh_token: auth.refresh_token })
console.log(`Created local QA owner #${user.id}; draft gym IDs: ${gymIds.join(', ')}. No credentials logged.`)
const result = spawnSync(process.execPath, ['scripts/owner-browser-smoke.mjs'], { encoding: 'utf8', env: { ...process.env, FITIGO_TEST_EMAIL: email, FITIGO_TEST_PASSWORD: password, FITIGO_TEST_CREATE_GYM: '1' }, timeout: 180000 })
const output = (result.stdout || '') + (result.stderr || '')
writeFileSync(join(tmpdir(), 'fitigo-owner-browser-results.txt'), output, 'utf8')
console.log(output)
process.exitCode = result.status ?? 1