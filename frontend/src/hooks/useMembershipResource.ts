import { useResource } from './useResource'
import { ApiError } from '../services/client'
export function membershipError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code) return error.message
    if (error.status === 0) return 'Unable to connect. Check your internet connection and try again.'
    if (error.status === 401) return 'Your session has expired. Please sign in again.'
    if (error.status === 403) return 'This information is not available for your account.'
    if (error.status === 404) return 'This membership or gym is no longer available.'
    if (error.status === 429) return 'Please wait a moment before trying again.'
  }
  return 'Unable to load your membership information. Please try again.'
}
export function useMembershipResource<T>(loader: () => Promise<T>, key: string) {
  return useResource(async () => { try { return await loader() } catch (error) { throw new Error(membershipError(error)) } }, key)
}