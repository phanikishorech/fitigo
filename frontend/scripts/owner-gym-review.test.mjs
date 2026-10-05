import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('../src/owner/gymReview.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText
const { canSubmitGym, gymRejectionMessage } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('resubmission requires explicit backend capability', () => {
  assert.equal(canSubmitGym({status:'REJECTED'}),false)
  assert.equal(canSubmitGym({status:'REJECTED',can_submit_for_approval:false}),false)
  assert.equal(canSubmitGym({status:'REJECTED',can_submit_for_approval:true}),true)
  assert.equal(canSubmitGym({status:'DRAFT'}),true)
  assert.equal(canSubmitGym({status:'DRAFT',can_submit_for_approval:false}),false)
  for(const status of ['PENDING_APPROVAL','APPROVED','SUSPENDED','INACTIVE']) assert.equal(canSubmitGym({status}),false)
})
test('owner rejection message displays backend reason without technical wording', () => {
  const message = gymRejectionMessage({status:'REJECTED',rejection_reason:'  Correct the address.  ',can_submit_for_approval:false})
  assert.match(message,/Reason: Correct the address\./)
  assert.match(message,/resubmission is not available yet/)
  assert.doesNotMatch(message,/API/)
  assert.match(gymRejectionMessage({status:'REJECTED',rejection_reason:null}),/No rejection reason was provided/)
  assert.match(gymRejectionMessage({status:'REJECTED',can_submit_for_approval:true}),/then resubmit for approval/)
})
test('detail view and edit review use the same backend capability and existing submission API', () => {
  const page = readFileSync(new URL('../src/owner/Gyms.tsx',import.meta.url),'utf8')
  assert.equal((page.match(/canSubmitGym\(gym\)/g)||[]).length,2)
  assert.match(page,/gymRejectionMessage\(gym\)/)
  assert.equal((page.match(/api.submitGymForApproval\(/g)||[]).length,2)
  assert.doesNotMatch(page,/dangerouslySetInnerHTML/)
})