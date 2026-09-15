export type LocationContext = {
  location_name: string
  latitude: number
  longitude: number
  city?: string
  state?: string
  country?: string
}

export type GymFacility = {
  id: number
  name: string
  description?: string | null
  icon?: string | null
}

export type GymDiscoverItem = {
  gym_id: number
  gym_name: string
  primary_image?: string | null
  images?: string[]
  latitude?: string | null
  longitude?: string | null
  address?: string | null
  locality?: string | null
  city?: string | null
  distance_km?: number | null
  average_rating?: number | null
  review_count: number
  facilities: GymFacility[]
  is_featured: boolean
  membership_access_status?:
    | 'INCLUDED'
    | 'UPGRADE_REQUIRED'
    | 'DAY_PASS_AVAILABLE'
    | 'NO_ACTIVE_MEMBERSHIP'
    | 'UNAVAILABLE'
    | string
    | null
  required_membership_tier?: string | null
  active_promotion?: string | null
  is_open_now?: boolean | null
}

export type GymDiscoverResponse = {
  total_count: number
  page: number
  page_size: number
  has_more: boolean
  gyms: GymDiscoverItem[]
}
