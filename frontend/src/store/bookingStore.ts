import { useSyncExternalStore } from 'react'
import { localDate } from '../services/client'
export type BookingDraft = { gymId: number; accessType: 'GYM' | 'CLASS'; date: string; memberCount: number; start: string; end: string; classId: number | null }
const drafts = new Map<string, BookingDraft>()
const listeners = new Set<() => void>()
export function getDraft(gymId: number, companionsDate?: string): BookingDraft {
  const key = `${gymId}:${companionsDate || 'regular'}`
  if (!drafts.has(key)) drafts.set(key, { gymId, accessType: 'GYM', date: companionsDate || localDate(), memberCount: 1, start: '', end: '', classId: null })
  return drafts.get(key)!
}
export function updateDraft(gymId: number, values: Partial<BookingDraft>, companionsDate?: string) {
  drafts.set(`${gymId}:${companionsDate || 'regular'}`, { ...getDraft(gymId, companionsDate), ...values, gymId, ...(companionsDate ? { date: companionsDate, accessType: 'GYM', classId: null } as const : {}) })
  listeners.forEach(listener => listener())
}
export function useBookingDraft(gymId: number, companionsDate?: string) {
  const draft = useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener) }, () => getDraft(gymId, companionsDate))
  return [draft, (values: Partial<BookingDraft>) => updateDraft(gymId, values, companionsDate)] as const
}