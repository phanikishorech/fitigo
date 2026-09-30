// Short-lived read cache only. Never cache QR, wallet, session or booking responses.
const entries = new Map<string, { expires: number; promise: Promise<unknown> }>()
export function cachedRead<T>(key: string, loader: () => Promise<T>, ttl = 30000): Promise<T> {
  const existing = entries.get(key)
  if (existing && existing.expires > Date.now()) return existing.promise as Promise<T>
  if (entries.size >= 100) entries.delete(entries.keys().next().value!)
  const promise = loader().catch(error => { if (entries.get(key)?.promise === promise) entries.delete(key); throw error })
  entries.set(key, { expires: Date.now() + ttl, promise })
  return promise
}
export function clearReadCache() { entries.clear() }