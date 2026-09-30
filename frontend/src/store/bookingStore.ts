import { useSyncExternalStore } from 'react'
import { localDate } from '../services/client'
export type BookingDraft = { gymId: number; accessType: 'GYM' | 'CLASS'; date: string; memberCount: number; start: string; end: string; classId: number | null }
const drafts = new Map<number, BookingDraft>()
const listeners = new Set<() => void>()
export function getDraft(gymId: number): BookingDraft {
  if (!drafts.has(gymId)) drafts.set(gymId, { gymId, accessType: 'GYM', date: localDate(), memberCount: 1, start: '', end: '', classId: null })
  return drafts.get(gymId)!
}
export function updateDraft(gymId: number, values: Partial<BookingDraft>) {
  drafts.set(gymId, { ...getDraft(gymId), ...values, gymId })
  listeners.forEach(listener => listener())
}
export function useBookingDraft(gymId: number) {
  const draft = useSyncExternalStore(listener => { listeners.add(listener); return () => listeners.delete(listener) }, () => getDraft(gymId))
  return [draft, (values: Partial<BookingDraft>) => updateDraft(gymId, values)] as const
}