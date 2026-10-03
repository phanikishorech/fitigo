// Real backend read-only contract checks. Does not generate QR, buy plans, pause, or check in.
// Optional FITIGO_TEST_EMAIL/PASSWORD enables authenticated reads through existing login.
import assert from 'node:assert/strict'
const base=process.env.FITIGO_API_ORIGIN||'http://localhost:8000'
let tokens=null
async function request(path, init={}) {
  const response=await fetch(`${base}/api/v1${path}`,{...init,headers:{...(tokens?{Authorization:`Bearer ${tokens.access_token}`}:{ }),...init.headers},signal:AbortSignal.timeout(15000)})
  if(!response.ok)throw new Error(`Live API ${path.split('?')[0]} returned HTTP ${response.status}`)
  return response.status===204?null:response.json()
}
try {
  const schemaResponse=await fetch(`${base}/api/v1/openapi.json`,{signal:AbortSignal.timeout(15000)})
  if(!schemaResponse.ok)throw new Error(`Live OpenAPI returned HTTP ${schemaResponse.status}`)
  const schema=await schemaResponse.json()
  assert.ok(schema.paths,'Live OpenAPI response has no path definitions')
  for(const path of ['/api/v1/memberships/me','/api/v1/profile/membership','/api/v1/customer/access-calendar','/api/v1/customer/access/today','/api/v1/gyms/discover','/api/v1/gyms/{gym_id}/details'])assert.ok(schema.paths[path],`Missing contract: ${path}`)
  const pausePaths=Object.keys(schema.paths).filter(path=>/pause/i.test(path)); console.log(`Live OpenAPI verified; exposed pause endpoints: ${pausePaths.length}`)
  const discovery=await request('/gyms/discover?page=1&page_size=1');assert.ok(Array.isArray(discovery.gyms))
  if(discovery.gyms[0]) {
    const id=discovery.gyms[0].gym_id;const [gym,plans]=await Promise.all([request(`/gyms/${id}/details`),request(`/memberships/gyms/${id}/plans`)])
    assert.equal(gym.gym_id,id);assert.ok(gym.membership_access);assert.ok(Array.isArray(plans))
  }
  console.log('PASS LIVE: public discovery, available gym detail and membership-plan response shapes')
  if(process.env.FITIGO_TEST_EMAIL&&process.env.FITIGO_TEST_PASSWORD) {
    tokens=await request('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:process.env.FITIGO_TEST_EMAIL,password:process.env.FITIGO_TEST_PASSWORD})})
    const now=new Date();const [identity,memberships,summary,calendar]=await Promise.all([request('/users/me'),request('/memberships/me'),request('/profile/membership'),request(`/customer/access-calendar?year=${now.getUTCFullYear()}&month=${now.getUTCMonth()+1}`)])
    assert.ok(identity.id);assert.ok(Array.isArray(memberships));assert.ok('membership_scope' in summary);assert.ok(Array.isArray(calendar.days))
    console.log('PASS LIVE: authenticated membership and read-only access calendar; no QR minted or business state changed')
  }else console.log('SKIP LIVE authenticated checks: provide FITIGO_TEST_EMAIL and FITIGO_TEST_PASSWORD for a dedicated test customer')
}finally {
  if(tokens?.refresh_token)await request('/auth/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:tokens.refresh_token})})
}