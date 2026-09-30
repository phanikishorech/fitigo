import { useEffect, useRef, useState } from 'react'
import { useResource } from '../hooks/useResource'
import { adminError } from './services'
import { navigate } from '../router'

export function useAdminResource<T>(loader: (signal: AbortSignal) => Promise<T>, key: string) {
  const controller = useRef<AbortController>()
  useEffect(() => () => controller.current?.abort(), [])
  return useResource(async () => {
    controller.current?.abort(); controller.current = new AbortController()
    try { return await loader(controller.current.signal) } catch (error) { throw new Error(adminError(error)) }
  }, key)
}
export function useDebounced<T>(value: T, delay = 350) {
  const [settled, setSettled] = useState(value)
  useEffect(() => { const timer = window.setTimeout(() => setSettled(value), delay); return () => clearTimeout(timer) }, [value, delay])
  return settled
}
export function useListQuery() {
  const query = new URLSearchParams(window.location.search)
  const [search, setSearch] = useState(query.get('q') || '')
  const settled = useDebounced(search)
  useEffect(() => {
    const current = new URLSearchParams(window.location.search)
    if (settled === (current.get('q') || '')) return
    settled ? current.set('q', settled) : current.delete('q'); current.delete('page')
    navigate(`${window.location.pathname}${current.size ? `?${current}` : ''}`)
  }, [settled])
  useEffect(() => { setSearch(query.get('q') || '') }, [window.location.search])
  const update = (values: Record<string, string>) => {
    const next = new URLSearchParams(window.location.search); next.delete('page')
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
    navigate(`${window.location.pathname}${next.size ? `?${next}` : ''}`)
  }
  const parsed = Number(query.get('page') || 1)
  const page = Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 1
  return { query, search, setSearch, update, page, offset: (page - 1) * 20, searching: settled !== search }
}