import { useState } from 'react'
import { useOwner } from './context'
import { ownerService } from './services'
import { useResource } from '../hooks/useResource'
import { Button, Card, EmptyState, ErrorState, Input, Notice, PageHeader, Skeleton } from './UI'
import Icon from '../components/common/Icon'
import { useContinuousScanner } from './useContinuousScanner'
import './scanner.css'

export default function CheckIn() {
  const { gymId, roles, gym } = useOwner()
  const assignments = useResource(() => roles.includes('GYM_STAFF') ? ownerService.staffGyms() : Promise.resolve([]), `scanner-assignments:${roles.join(',')}`)
  if (assignments.loading) return <Skeleton />
  if (assignments.error) return <ErrorState message={assignments.error} retry={assignments.retry} />
  if (!gymId) return <EmptyState title="Select a gym to check in members" />
  if (!roles.includes('GYM_STAFF') || !assignments.data?.some(g => g.id === gymId)) return <div className="ow-stack"><PageHeader title="Member check-in" description="Secure access starts with the right permissions." /><Card><EmptyState title="Assigned staff access required" description="The current QR endpoint accepts only a GYM_STAFF account assigned to this gym. Owner access alone does not authorize check-in. Sign in with an assigned staff account to scan member QR codes." /></Card></div>
  return <Scanner key={gymId} gymId={gymId} gymName={gym?.name || ''} />
}
function Scanner({ gymId, gymName }: { gymId: number; gymName: string }) {
  const scanner = useContinuousScanner(gymId)
  const { context, video } = scanner
  const [token, setToken] = useState('')
  const result = context.validationResult
  const verificationError = context.error?.kind === 'verification'
  const busy = context.isProcessingScan || verificationError || context.state === 'CAMERA_READY'
  return <div className={`ow-scanner-page ow-stack ${context.cameraAttached ? 'is-scanning' : ''}`} data-scanner-state={context.state}>
    <PageHeader title="Scan member QR" description={`${gymName} · Point the camera at the member's QR code.`} />
    <Card className="ow-scanner-card">
      <div className="ow-camera">
        <video ref={video} muted playsInline aria-label="QR scanner camera" onError={scanner.cameraFailed} />
        {!context.cameraAttached && <div className="ow-camera-placeholder"><Icon name="qr" size={76} /><h2>{context.state === 'CAMERA_ERROR' ? 'Unable to access the camera' : context.state === 'CAMERA_READY' ? 'Opening camera…' : 'Camera access required'}</h2><p>Position the member QR inside the frame.</p></div>}
        <div className="ow-camera-frame" aria-hidden="true" />
        <div className="ow-scan-live" role="status" aria-live="polite" aria-atomic="true">
          {context.state === 'SCANNING' && !verificationError && <span className="ow-scan-ready">Ready to scan</span>}
          {context.state === 'VALIDATING' && <div className="ow-scan-overlay ow-scan-overlay--info"><Icon name="shield" size={28} /><h2>Checking access…</h2><p>Please wait for verification.</p></div>}
          {result && (context.state === 'APPROVED' || context.state === 'REJECTED') && <div className={`ow-scan-overlay ow-scan-overlay--${result.success ? 'success' : 'error'}`}>
            <span className={`ow-result-icon ${result.success ? '' : 'is-error'}`}><Icon name={result.success ? 'check' : 'close'} size={32} /></span>
            <h2>{result.success ? 'ACCESS APPROVED' : 'ACCESS REJECTED'}</h2>
            {result.success ? <><h3>{result.customer_name}</h3><p>{result.access_type === 'MULTI_GYM' ? 'FitiGo Multi-Gym' : result.access_type === 'SINGLE_GYM' ? 'Single-Gym membership' : result.access_type.replaceAll('_', ' ')}</p><p>{result.gym_name}</p><strong>Entry allowed</strong></> : <p>{result.message}</p>}
          </div>}
          {verificationError && <div className="ow-scan-overlay ow-scan-overlay--info"><Icon name="shield" size={28} /><h2>Unable to verify access</h2><p>Please try again.</p></div>}
        </div>
      </div>
      <div className="ow-stack ow-scanner-controls">
        <p className="ow-muted">Position the member’s QR inside the frame. Scanning resumes automatically after each result.</p>
        {context.cameraAttached ? <Button variant="secondary" onClick={scanner.stop}><Icon name="close" />Stop camera</Button> : <Button disabled={busy} onClick={() => void scanner.initialize()}><Icon name="qr" />{context.state === 'CAMERA_ERROR' ? 'Try Again' : context.state === 'CAMERA_READY' ? 'Opening camera…' : 'Allow Camera'}</Button>}
        {context.error && <Notice tone={verificationError ? 'info' : 'error'}>{context.error.message}</Notice>}
        <details><summary>Use a QR token instead</summary><form className="ow-stack" onSubmit={event => { event.preventDefault(); if (scanner.detected(token.trim(), true)) setToken('') }}>
          <Input label="QR token" value={token} onChange={event => setToken(event.target.value)} autoComplete="off" required disabled={busy} />
          <Button type="submit" disabled={busy || !token.trim()}>Validate QR</Button>
        </form></details>
        <p className="ow-scanner-note"><Icon name="shield" size={16} />Entry is allowed only after backend confirmation.</p>
      </div>
    </Card>
  </div>
}
