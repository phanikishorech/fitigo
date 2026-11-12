import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
const read=path=>readFileSync(new URL('../src/'+path,import.meta.url),'utf8')
test('admin uses a filtered lookahead page, not an unfiltered extra query',()=>{
 const s=read('admin/Users.tsx');assert.match(s,/role: role \|\| undefined, offset: list.offset, limit: 21/)
 assert.doesNotMatch(s,/Promise.all|within each server page/)
 assert.match(s,/reason_code: reason/)
})
test('photo deletion requires confirmation and has honest pending cleanup',()=>{
 const s=read('owner/PhotoRemoval.tsx')
 assert.match(s,/ConfirmDialog title="Remove saved photo\?"/)
 assert.match(s,/if \(!jobs.data\?\.enabled\)/)
 assert.match(s,/result.file_deleted \?/)
 assert.match(s,/Retry file cleanup/)
 assert.match(s,/await request<Job>/)
})
test('account delivery is queried, not permanently described as unconfigured',()=>{
 assert.match(read('components/common/AccountDeliveryNotice.tsx'),/\/auth\/otp\/options/)
 assert.doesNotMatch(read('pages/profile/SettingsPage.tsx'),/OTP delivery is not configured/)
 assert.match(read('admin/WorkflowSettings.tsx'),/operational_audit_enabled/)
})