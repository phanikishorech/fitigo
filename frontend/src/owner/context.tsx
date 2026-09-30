import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { fetchOwnerGyms, type OwnerGymListItem } from '../screens/GymOwner/api'
import { useResource } from '../hooks/useResource'
import type { User } from '../services/accountService'
import { ownerService } from './services'
import { navigate } from '../router'
import { switchedGymPath } from './routes'

type GymChoice = Pick<OwnerGymListItem, 'id' | 'name' | 'city'> & Partial<OwnerGymListItem>
type OwnerContext = { user: User; roles: string[]; gyms: GymChoice[]; gym: GymChoice | undefined; gymId: number | undefined; loading: boolean; error: string; refreshGyms: () => void; selectGym: (id: number) => void; syncGym: (id: number) => void; toast: (message: string) => void }
const Context = createContext<OwnerContext | null>(null)
export function useOwner() { const value = useContext(Context); if (!value) throw new Error('Owner provider is required'); return value }
export function OwnerProvider({ user, roles, routeGymId, children }: { user: User; roles: string[]; routeGymId?: number; children: ReactNode }) {
  const owner = roles.includes('GYM_OWNER')
  const resource = useResource<GymChoice[]>(() => owner ? fetchOwnerGyms() : ownerService.staffGyms(), `owner-gyms:${user.id}:${owner}`)
  const storageKey = `fitigo:owner:${user.id}:gym`
  const [selected, setSelected] = useState<number | undefined>(() => { try { return Number(localStorage.getItem(storageKey)) || undefined } catch { return undefined } })
  const [message, setMessage] = useState('')
  // Keep the shell and active forms mounted during a post-save list refresh.
  const previous = useRef<GymChoice[] | null>(null)
  if (resource.data) previous.current = resource.data
  const gyms = resource.data || previous.current || []
  const gym = gyms.find(g => g.id === (routeGymId ?? selected)) || (!routeGymId ? gyms[0] : undefined)
  useEffect(() => { if (gym) { setSelected(gym.id); try { localStorage.setItem(storageKey, String(gym.id)) } catch { /* session selection still works */ } } }, [gym?.id, storageKey])
  useEffect(() => { if (message) { const timer = setTimeout(() => setMessage(''), 5000); return () => clearTimeout(timer) } }, [message])
  const selectGym = (id: number) => { if (!gyms.some(g => g.id === id)) return; setSelected(id); navigate(switchedGymPath(window.location.pathname, id)) }
  return <Context.Provider value={{ user, roles, gyms, gym, gymId: gym?.id, loading: resource.loading && !previous.current, error: previous.current ? '' : resource.error, refreshGyms: resource.retry, selectGym, syncGym: setSelected, toast: setMessage }}>{resource.error && previous.current && <div className="ow-refresh-error" role="alert">Unable to refresh your gym list. <button type="button" onClick={resource.retry}>Try again</button></div>}{children}{message && <div className="ow-toast" role="status">{message}<button type="button" aria-label="Dismiss notification" onClick={() => setMessage('')}>×</button></div>}</Context.Provider>
}