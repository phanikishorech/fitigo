import assert from 'node:assert/strict'
import test from 'node:test'
import {readFileSync} from 'node:fs'
const read=p=>readFileSync(new URL('../src/'+p,import.meta.url),'utf8')
test('preferences and read state use authenticated server mutations',()=>{
 const s=read('components/common/NotificationCenter.tsx')
 assert.match(s,/\/notifications\/preferences/)
 assert.match(s,/method: 'PATCH'/)
 assert.match(s,/\/notifications\/inbox\/\$\{item.id\}\/read/)
 assert.match(s,/await request/)
 assert.match(s,/Security notices are not optional/)
 assert.match(s,/not delivered to an inbox/)
 assert.match(s,/Uncertain sends are not automatically resent/)
})
test('all workspaces expose notification controls with a disabled deployment state',()=>{
 for(const p of ['owner/Account.tsx','admin/Account.tsx','pages/profile/SettingsPage.tsx'])assert.match(read(p),/NotificationCenter/)
 assert.match(read('components/common/NotificationCenter.tsx'),/if \(!data.enabled\)/)
 assert.doesNotMatch(read('owner/Account.tsx'),/Read\/unread tracking is not provided/)
})
test('support contact comes from backend rather than invented contact details',()=>{
 assert.match(read('components/common/SupportContact.tsx'),/\/meta\/support/)
 assert.match(read('components/common/SupportContact.tsx'),/Never send passwords/)
})