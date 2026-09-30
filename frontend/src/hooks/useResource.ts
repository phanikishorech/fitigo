import { useCallback, useEffect, useRef, useState } from 'react'

export function useResource<T>(loader: () => Promise<T>, key: string) {
  const load = useRef(loader)
  load.current = loader
  const [version, setVersion] = useState(0)
  const [state, setState] = useState<{ key: string; loading: boolean; data: T | null; error: string }>({ key, loading: true, data: null, error: '' })
  useEffect(() => {
    let active = true
    setState({ key, loading: true, data: null, error: '' })
    load.current().then(data => { if (active) setState({ key, loading: false, data, error: '' }) })
      .catch(error => { if (active) setState({ key, loading: false, data: null, error: error instanceof Error ? error.message : 'Something went wrong. Please try again.' }) })
    return () => { active = false }
  }, [key, version])
  const retry = useCallback(() => setVersion(v => v + 1), [])
  return { ...(state.key === key ? state : { loading: true, data: null, error: '' }), retry }
}

export function useMutation() {
  const lock = useRef(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function run(action: () => Promise<void>) {
    if (lock.current) return
    lock.current = true; setPending(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : 'Unable to complete this request.') }
    finally { lock.current = false; setPending(false) }
  }
  return { pending, error, run, setError }
}