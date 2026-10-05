import { useEffect, useRef, useState } from 'react'
import { useOwner } from './context'
import { ownerService, type CheckInResult } from './services'
import { useMutation, useResource } from '../hooks/useResource'
import { Button, Card, EmptyState, ErrorState, Input, Notice, PageHeader, Skeleton, StatusBadge } from './UI'
import Icon from '../components/common/Icon'
import { safeError } from '../services/client'

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
  const video = useRef<HTMLVideoElement>(null); const stream = useRef<MediaStream | null>(null); const timer = useRef<ReturnType<typeof setTimeout>>(); const generation = useRef(0)
  const [camera, setCamera] = useState(false); const [starting, setStarting] = useState(false); const [cameraError, setCameraError] = useState(''); const [token, setToken] = useState(''); const [result, setResult] = useState<CheckInResult | null>(null)
  const mutation = useMutation(); const requestLock = useRef(false); const alive = useRef(true); const startLock = useRef(false)
  function release() { generation.current++; if (timer.current) clearTimeout(timer.current); timer.current = undefined; stream.current?.getTracks().forEach(t => t.stop()); stream.current = null; if (video.current) video.current.srcObject = null; startLock.current = false }
  function stop() { release(); setCamera(false); setStarting(false) }
  useEffect(() => { alive.current = true; const onHide = () => { if (document.hidden) stop() }; document.addEventListener('visibilitychange', onHide); return () => { alive.current = false; release(); document.removeEventListener('visibilitychange', onHide) } }, [])
  async function validate(value: string) {
    if (requestLock.current) return
    requestLock.current = true; stop(); setToken('')
    await mutation.run(async () => { const data = await ownerService.checkIn(gymId, value); if (alive.current) setResult(data) })
    requestLock.current = false
  }
  async function start() {
    if (startLock.current || requestLock.current || stream.current) return
    startLock.current = true
    setStarting(true); setCameraError(''); const run = ++generation.current
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Camera access requires HTTPS and a supported browser. You can paste the member QR token below.')
      // Lazy-load the decoder only for camera users. The canvas never enters the DOM.
      const { default: decode } = await import('jsqr').catch(() => { throw new Error('Unable to initialize QR scanning. Restart scanning or paste the QR token.') })
      if (!alive.current || generation.current !== run) return
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d', { willReadFrequently: true })
      if (!context) throw new Error('Unable to initialize QR scanning. Restart scanning or paste the QR token.')
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      if (!alive.current || generation.current !== run) { media.getTracks().forEach(t => t.stop()); return }
      stream.current = media; if (!video.current) { stop(); return }; video.current.srcObject = media; await video.current.play()
      if (generation.current !== run) return
      setCamera(true); setStarting(false); startLock.current = false
      const scan = async () => {
        if (!alive.current || generation.current !== run || !video.current) return
        try {
          const source = video.current
          // Empty/not-yet-ready frames are normal while the camera starts.
          if (source.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && source.videoWidth && source.videoHeight) {
            const scale = Math.min(1, 960 / Math.max(source.videoWidth, source.videoHeight))
            canvas.width = Math.max(1, Math.round(source.videoWidth * scale)); canvas.height = Math.max(1, Math.round(source.videoHeight * scale))
            context.drawImage(source, 0, 0, canvas.width, canvas.height)
            const frame = context.getImageData(0, 0, canvas.width, canvas.height)
            const code = decode(frame.data, frame.width, frame.height, { inversionAttempts: 'attemptBoth' })
            if (code?.data) { await validate(code.data); return }
          }
        } catch { if (generation.current !== run) return; stop(); setCameraError('The camera could not read the image. Restart scanning or paste the QR token.'); return }
        timer.current = setTimeout(() => void scan(), 350)
      }
      void scan()
    } catch (e) { if (!alive.current || generation.current !== run) return; stop(); setCameraError(e instanceof DOMException ? e.name === 'NotAllowedError' ? 'Camera permission was denied. Allow camera access in your browser settings or paste the QR token.' : e.name === 'NotReadableError' || e.name === 'AbortError' ? 'The camera is busy or could not start. Close other camera apps and try again, or paste the QR token.' : 'No usable camera was found. Check your device or paste the QR token.' : e instanceof Error ? e.message : 'Unable to start the camera.') }
  }
  return <div className={`ow-scanner-page ow-stack ${camera ? 'is-scanning' : ''}`}><PageHeader title="Scan member QR" description={`${gymName} · Point the camera at the member's QR code.`} /><Card className="ow-scanner-card">{result ? <div className="ow-result ow-stack"><span className={`ow-result-icon ${result.success ? '' : 'is-error'}`}><Icon name={result.success ? 'check' : 'close'} size={42} /></span><h2>{result.success ? 'Check-in successful' : 'Access denied'}</h2><StatusBadge status={result.status} />{result.success ? <><h3>{result.customer_name}</h3><p>{result.gym_name}</p><p>{result.access_type.replace(/_/g, ' ')}</p><p>{new Date(result.checkin_time).toLocaleString()}</p><Notice tone="success">Access validated and check-in recorded by FitiGo. The QR token has been consumed.</Notice></> : <Notice tone="error">{safeError(400, result.message)}</Notice>}<Button onClick={() => { setResult(null); mutation.setError('') }}>Scan another</Button></div> : <><div className="ow-camera"><video ref={video} muted playsInline aria-label="QR scanner camera" />{!camera && <div className="ow-camera-placeholder"><Icon name="qr" size={76} /><h2>{mutation.pending ? 'Validating access…' : 'Ready when you are'}</h2><p>{mutation.pending ? 'Please wait for the check-in result.' : 'Position the member QR inside the frame.'}</p></div>}<div className="ow-camera-frame" aria-hidden="true" /></div><div className="ow-stack ow-scanner-controls">{mutation.pending ? <Notice>Validating access and recording check-in…</Notice> : <Button loading={starting} onClick={() => camera ? stop() : void start()}><Icon name={camera ? 'close' : 'qr'} />{camera ? 'Stop camera' : 'Start camera'}</Button>}{cameraError && <Notice>{cameraError}</Notice>}{mutation.error && <Notice tone="error">{mutation.error} If the connection was interrupted, the check-in may have completed. Scan again to confirm the backend state.</Notice>}<details><summary>Use a QR token instead</summary><form className="ow-stack" onSubmit={e => { e.preventDefault(); void validate(token.trim()) }}><p className="ow-caption">Paste the QR value from a scanner. This is not a member ID override; all access checks still run on the server.</p><Input label="Member QR token" type="password" autoComplete="off" minLength={10} required value={token} onChange={e => setToken(e.target.value)} disabled={mutation.pending} /><Button variant="secondary" type="submit" loading={mutation.pending}>Validate & check in</Button></form></details></div></>}</Card><p className="ow-scanner-note"><Icon name="shield" size={16} />Access is always validated by FitiGo. QR values are not saved on this device.</p></div>
}