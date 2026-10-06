import { useEffect, useRef, useState } from 'react'
import { useMutation } from '../../hooks/useResource'
import { post } from '../../services/client'
import { useIdentity } from '../../session/SessionGuard'
import { Alert, Badge, Button, EmptyState, ErrorState, Heading, Link, Skeleton } from '../../components/common/UI'

type Checkin = { success: true; customer_name: string; gym_name: string; access_type: string; checkin_time: string } | { success: false; status: string; message: string }
type Detector = { detect: (video: HTMLVideoElement) => Promise<{ rawValue: string }[]> }
type DetectorConstructor = new (options: { formats: string[] }) => Detector
export default function StaffPage() {
  useIdentity() // Authentication and portal access are enforced by the central guard.
  return <Scanner />
}
function Scanner() {
  const [gymId, setGymId] = useState('')
  const [scanning, setScanning] = useState(false)
  const [cameraError, setCameraError] = useState('')
  const [result, setResult] = useState<Checkin | null>(null)
  const video = useRef<HTMLVideoElement>(null)
  const mutation = useMutation()
  const detectorClass = (window as unknown as { BarcodeDetector?: DetectorConstructor }).BarcodeDetector
  useEffect(() => {
    if (!scanning || !detectorClass) return
    let active = true, stream: MediaStream | null = null, timer: ReturnType<typeof setTimeout> | undefined
    const detector = new detectorClass({ formats: ['qr_code'] })
    async function detect() {
      if (!active || !video.current) return
      try {
        const codes = await detector.detect(video.current)
        if (!active) return
        if (codes[0]) {
          setScanning(false)
          await mutation.run(async () => { setResult(await post<Checkin>('/checkins/validate', { gym_id: Number(gymId), qr_token: codes[0].rawValue })) })
          return
        }
        timer = setTimeout(detect, 250)
      } catch { if (active) { setCameraError('Unable to read the camera. Please try again.'); setScanning(false) } }
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false }).then(async value => {
      stream = value
      if (!active) { value.getTracks().forEach(track => track.stop()); return }
      if (video.current) { video.current.srcObject = value; await video.current.play(); timer = setTimeout(detect, 300) }
    }).catch(() => { if (active) { setCameraError('Camera access failed. Allow camera permission and use a secure connection.'); setScanning(false) } })
    return () => { active = false; if (timer) clearTimeout(timer); stream?.getTracks().forEach(track => track.stop()) }
  }, [scanning, gymId])
  return <div className="fg-narrow"><Badge>FITIGO STAFF</Badge><Heading title="Scan member QR" subtitle="Validate gym entry through the access service." /><div className="fg-panel fg-stack"><label className="fg-field">Assigned gym ID<input type="number" min="1" value={gymId} disabled={scanning || mutation.pending} onChange={e => setGymId(e.target.value)} /><small>The backend verifies your staff assignment. Enter only the gym you’re checking members into.</small></label>{!detectorClass || !navigator.mediaDevices ? <Alert>Camera QR scanning is unavailable in this browser. Use a supported browser with native QR detection over HTTPS. No unvalidated entry can be recorded.</Alert> : <><video ref={video} muted playsInline aria-label="QR scanner camera" style={{ width: '100%', display: scanning ? 'block' : 'none', borderRadius: 12 }} /><Button loading={mutation.pending} disabled={!Number.isSafeInteger(Number(gymId)) || Number(gymId) < 1} onClick={() => { setResult(null); setCameraError(''); setScanning(value => !value) }}>{scanning ? 'Stop camera' : 'Start scanning'}</Button></>}{cameraError && <Alert>{cameraError}</Alert>}{mutation.error && <Alert>{mutation.error}</Alert>}{result && <section className={result.success ? 'fg-success fg-stack' : 'fg-alert fg-stack'} role="status"><h2>{result.success ? 'Check-in successful' : 'Entry rejected'}</h2>{result.success ? <><p>{result.customer_name}</p><p>{result.gym_name} · {result.access_type}</p><p>{new Date(result.checkin_time).toLocaleString()}</p></> : <p>{result.message}</p>}<Button variant="secondary" onClick={() => setResult(null)}>Done</Button></section>}</div><Link to="/owner" className="fg-inline-link">Back to owner area</Link></div>
}