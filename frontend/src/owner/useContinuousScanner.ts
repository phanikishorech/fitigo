import { useCallback, useEffect, useReducer, useRef } from 'react'
import { ownerService } from './services'
import { initialScannerState, mayScan, normalizeCheckIn, RESULT_DISPLAY_MS, scannerReducer, VALIDATION_TIMEOUT_MS, type ScannerEvent } from './scannerMachine'

export function useContinuousScanner(gymId: number) {
  const [context, reactDispatch] = useReducer(scannerReducer, initialScannerState)
  const current = useRef(context)
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const decode = useRef<typeof import('jsqr').default>()
  const detectorTimer = useRef<ReturnType<typeof setTimeout>>()
  const resultTimer = useRef<ReturnType<typeof setTimeout>>()
  const requestTimer = useRef<ReturnType<typeof setTimeout>>()
  const request = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const alive = useRef(false)
  const starting = useRef(false)
  const inFlightCycle = useRef<number | null>(null)
  const trackListeners = useRef<(() => void) | null>(null)

  // Synchronous reducer mirror closes the gap before React commits a render.
  // Both mirrors use the same pure reducer; callbacks never assign state fields.
  const dispatch = useCallback((event: ScannerEvent) => {
    if (!alive.current) return false
    const next = scannerReducer(current.current, event)
    if (next === current.current) return false
    current.current = next; reactDispatch(event); return true
  }, [])
  const cleanupCamera = useCallback(() => {
    generation.current++; starting.current = false
    clearTimeout(detectorTimer.current); clearTimeout(resultTimer.current); clearTimeout(requestTimer.current)
    request.current?.abort(); request.current = null; inFlightCycle.current = null
    trackListeners.current?.(); trackListeners.current = null
    stream.current?.getTracks().forEach(track => track.stop()); stream.current = null
    if (video.current) video.current.srcObject = null
  }, [])
  const failCamera = useCallback((permission: boolean, message: string) => {
    cleanupCamera()
    dispatch({ type: permission ? 'CAMERA_PERMISSION_DENIED' : 'CAMERA_FAILED', error: { kind: permission ? 'permission' : 'camera', message } })
  }, [cleanupCamera, dispatch])

  const initialize = useCallback(async () => {
    if (!alive.current || starting.current || stream.current || current.current.isProcessingScan || document.hidden) return
    starting.current = true
    const run = ++generation.current
    const valid = () => alive.current && generation.current === run
    try {
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw new Error('Camera access is unavailable. Use a camera-capable browser on a secure connection, or enter a QR token below.')
      decode.current = (await import('jsqr')).default
      if (!valid()) return
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      if (!valid()) { media.getTracks().forEach(track => track.stop()); return }
      stream.current = media
      dispatch({ type: 'CAMERA_PERMISSION_GRANTED' })
      const lost = () => { if (valid()) failCamera(false, 'The camera stopped unexpectedly. Please try again.') }
      media.getVideoTracks().forEach(track => track.addEventListener('ended', lost))
      trackListeners.current = () => media.getVideoTracks().forEach(track => track.removeEventListener('ended', lost))
      if (!video.current) throw new Error('Unable to initialize the camera preview. Please try again.')
      video.current.srcObject = media
      await video.current.play()
      if (!valid()) return
      if (!media.getVideoTracks().some(track => track.readyState === 'live')) throw new Error('The camera stopped unexpectedly. Please try again.')
      starting.current = false
      dispatch({ type: 'CAMERA_INITIALIZED' })
    } catch (error) {
      if (!valid()) return
      const name = error instanceof DOMException ? error.name : ''
      const permission = name === 'NotAllowedError' || name === 'SecurityError'
      failCamera(permission, permission ? 'Camera permission is required to scan QR codes. Allow camera access in your browser settings, then select Allow Camera.' : name === 'NotReadableError' || name === 'AbortError' ? 'The camera is busy. Close other camera apps and try again.' : name === 'NotFoundError' ? 'No camera was found. Connect a camera or use a QR token instead.' : 'Unable to access the camera. Please try again or use a QR token instead.')
    }
  }, [dispatch, failCamera])

  useEffect(() => {
    alive.current = true
    let disposed = false; let permission: PermissionStatus | undefined
    // Deferring avoids duplicate permission requests during StrictMode effect replay.
    const startup = setTimeout(() => void (async () => {
      try {
        permission = await navigator.permissions?.query({ name: 'camera' as PermissionName })
        if (disposed) return
        if (permission) permission.onchange = () => {
          if (permission?.state === 'granted') void initialize()
          else failCamera(true, 'Camera permission is required to scan member QR codes.')
        }
        if (permission?.state === 'denied') { failCamera(true, 'Camera permission is required. Enable it in browser settings, then select Allow Camera.'); return }
      } catch { /* Some mobile browsers do not implement camera permission queries. */ }
      if (!disposed) void initialize()
    })(), 0)
    const visibility = () => {
      if (document.hidden) failCamera(false, 'Camera paused while this page was hidden. Select Try Again to resume.')
    }
    document.addEventListener('visibilitychange', visibility)
    return () => {
      disposed = true; clearTimeout(startup); if (permission) permission.onchange = null
      document.removeEventListener('visibilitychange', visibility)
      cleanupCamera(); dispatch({ type: 'SCANNER_UNMOUNTED' }); alive.current = false
    }
  }, [cleanupCamera, dispatch, failCamera, initialize])

  const detected = useCallback((value: string, manual = false) => {
    if (starting.current) return false
    const at = Date.now()
    if (!mayScan(current.current, value, at, manual)) return false
    return dispatch({ type: manual ? 'MANUAL_QR' : 'QR_DETECTED', qrValue: value, at })
  }, [dispatch])

  useEffect(() => {
    if (context.state !== 'SCANNING' || context.error?.kind === 'verification' || !context.cameraAttached) return
    let cancelled = false
    const canvas = document.createElement('canvas')
    const graphics = canvas.getContext('2d', { willReadFrequently: true })
    if (!graphics) { failCamera(false, 'Unable to initialize QR scanning. Please try again.'); return }
    const scan = () => {
      if (cancelled || current.current.state !== 'SCANNING') return
      try {
        if (!stream.current?.getVideoTracks().some(track => track.readyState === 'live')) { failCamera(false, 'The camera stopped unexpectedly. Please try again.'); return }
        const source = video.current
        if (source && source.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && source.videoWidth && source.videoHeight) {
          const scale = Math.min(1, 960 / Math.max(source.videoWidth, source.videoHeight))
          canvas.width = Math.max(1, Math.round(source.videoWidth * scale)); canvas.height = Math.max(1, Math.round(source.videoHeight * scale))
          graphics.drawImage(source, 0, 0, canvas.width, canvas.height)
          const frame = graphics.getImageData(0, 0, canvas.width, canvas.height)
          const value = decode.current?.(frame.data, frame.width, frame.height, { inversionAttempts: 'attemptBoth' })?.data || null
          dispatch({ type: 'FRAME_OBSERVED', value, at: Date.now() })
          if (value && detected(value)) return
        }
        detectorTimer.current = setTimeout(scan, 200)
      } catch { failCamera(false, 'The camera could not read the image. Please try again or enter the QR token.') }
    }
    scan()
    return () => { cancelled = true; clearTimeout(detectorTimer.current) }
  }, [context.state, context.cameraAttached, context.error?.kind, detected, dispatch, failCamera])

  useEffect(() => {
    if (context.state !== 'VALIDATING' || !context.scanValue || inFlightCycle.current === context.cycle) return
    const { cycle, scanValue } = context
    inFlightCycle.current = cycle
    const controller = new AbortController(); request.current = controller
    const errorEvent = () => dispatch({ type: 'VALIDATION_ERROR', cycle, at: Date.now(), error: { kind: 'verification', message: 'Unable to verify access. Please try again. If the connection was interrupted, check-in may have completed; scan again to confirm.' } })
    requestTimer.current = setTimeout(() => { controller.abort(); errorEvent() }, VALIDATION_TIMEOUT_MS)
    void ownerService.checkIn(gymId, scanValue, controller.signal).then(raw => {
      if (controller.signal.aborted || !alive.current) return
      const result = normalizeCheckIn(raw)
      if (!result) { errorEvent(); return }
      if (result.success) dispatch({ type: 'VALIDATION_APPROVED', cycle, result, at: Date.now() })
      else dispatch({ type: 'VALIDATION_REJECTED', cycle, result, at: Date.now() })
    }).catch(() => { if (!controller.signal.aborted && alive.current) errorEvent() })
      .finally(() => {
        if (request.current === controller) { clearTimeout(requestTimer.current); request.current = null }
      })
    // On any state change, invalidate in-flight work; abort cannot roll back a
    // check-in already committed by the backend. Cycle guards ignore late replies.
    return () => { controller.abort(); clearTimeout(requestTimer.current); if (request.current === controller) request.current = null }
  }, [context.state, context.cycle, context.scanValue, gymId, dispatch])

  useEffect(() => {
    const result = context.state === 'APPROVED' || context.state === 'REJECTED'
    if (!result && context.error?.kind !== 'verification') return
    resultTimer.current = setTimeout(() => dispatch({ type: result ? 'RESULT_TIMEOUT' : 'CLEAR_VERIFICATION_ERROR', cycle: context.cycle }), RESULT_DISPLAY_MS)
    return () => clearTimeout(resultTimer.current)
  }, [context.state, context.cycle, context.error?.kind, dispatch])

  return { context, video, initialize, detected,
    stop: () => failCamera(false, 'Camera stopped. Select Try Again to resume scanning.'),
    cameraFailed: () => failCamera(false, 'The camera stopped unexpectedly. Please try again.') }
}