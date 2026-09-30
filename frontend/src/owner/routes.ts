export type OwnerRoute = { page: string; gymId?: number; id?: number; mode?: 'create' | 'edit' }
export function ownerRoute(path: string): OwnerRoute {
  const clean = path.replace(/\/+$/, '')
  if (clean === '/owner') return { page: 'dashboard' }
  const simple = clean.match(/^\/owner\/(login|register|verify|dashboard|gyms|bookings|members|staff|check-in|revenue|analytics|settings|notifications|more|help)$/)
  if (simple) return { page: simple[1] }
  if (clean === '/owner/gyms/create') return { page: 'gymForm', mode: 'create' }
  if (clean === '/owner/staff/invite') return { page: 'staffForm', mode: 'create' }
  const gym = clean.match(/^\/owner\/gyms\/(\d+)(?:\/(edit|memberships|classes|slots)(?:\/(create|\d+)(?:\/(edit))?)?)?$/)
  if (gym) {
    const gymId = Number(gym[1]); const id = gym[3] && gym[3] !== 'create' ? Number(gym[3]) : undefined
    if (!Number.isSafeInteger(gymId) || gymId < 1 || (id !== undefined && (!Number.isSafeInteger(id) || id < 1))) return { page: 'notFound' }
    if (gym[2] === 'edit') return gym[3] ? { page: 'notFound' } : { page: 'gymForm', gymId, mode: 'edit' }
    if (gym[2] === 'slots' && gym[3]) return { page: 'notFound' }
    if (gym[4] && !id) return { page: 'notFound' }
    return { page: gym[2] || 'gym', gymId, id, mode: gym[3] === 'create' ? 'create' : gym[4] ? 'edit' : undefined }
  }
  const detail = clean.match(/^\/owner\/(bookings|members|staff)\/(\d+)$/)
  if (detail && Number.isSafeInteger(Number(detail[2])) && Number(detail[2]) > 0) return { page: `${detail[1]}Detail`, id: Number(detail[2]) }
  return { page: 'notFound' }
}

export function switchedGymPath(path: string, gymId: number) {
  const route = ownerRoute(path)
  if (['memberships', 'classes', 'slots'].includes(route.page)) return `/owner/gyms/${gymId}/${route.page}`
  if (route.gymId) return `/owner/gyms/${gymId}`
  if (route.page === 'bookingsDetail') return '/owner/bookings'
  if (route.page === 'membersDetail') return '/owner/members'
  if (route.page === 'staffDetail' || route.page === 'staffForm') return '/owner/staff'
  return path
}