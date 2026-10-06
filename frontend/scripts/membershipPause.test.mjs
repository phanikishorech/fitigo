import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const code = read('../src/services/membershipPauseService.ts').replace(/import .* from '.\/client'/, 'const request=(...args)=>globalThis.__pauseRequest(...args)')
const compiled = ts.transpileModule(code, {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const {membershipPauseService:service}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
test('pause uses existing request client and backend preview, not client expiry calculations',async()=>{
  const calls=[];globalThis.__pauseRequest=async(...args)=>{calls.push(args);return {}}
  await service.eligibility(42)
  await service.preview(42,{start_date:'2026-11-10',days:4})
  await service.confirm(42,{start_date:'2026-11-10',days:4,preview_token:'server-preview',new_end_at:'untrusted-client-expiry'},'request-key')
  assert.equal(calls[0][0],'/memberships/me/42/pause');assert.equal(calls[0][1].cache,'no-store')
  assert.equal(calls[1][0],'/memberships/me/42/pause/preview')
  assert.deepEqual(JSON.parse(calls[2][1].body),{start_date:'2026-11-10',days:4,accepted_preview:'server-preview'})
  assert.equal(calls[2][1].headers['Idempotency-Key'],'request-key')
})
test('customer pause controls use server eligibility, limits, dates and history',()=>{
  const ui=read('../src/components/membership/MembershipPause.tsx')
  for(const text of ['eligibility.can_pause','eligibility.pause_days_remaining','eligibility.eligible_from','eligibility.eligible_until','preview.new_end_at','saved.current_end_at','eligibility.history.map','lock.current'])assert.ok(ui.includes(text),text)
  assert.ok(!/setDate\(|getDate\(|86400000/.test(ui))
  assert.ok(ui.includes('Pause scheduled'))
  assert.ok(ui.includes('requestKey.current'))
})
test('admin and owner edit the policy through their existing plan configuration',()=>{
  const admin=read('../src/admin/MembershipPlans.tsx'), owner=read('../src/owner/Operations.tsx')
  assert.ok(admin.includes("change('pause_rule'"));assert.ok(admin.includes('adminMembershipPlans.update'))
  assert.ok(owner.includes('pause_policy: { allowed: pauseAllowed'))
  assert.ok(owner.includes('api.updateOwnerMembershipPlan'))
})