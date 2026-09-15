export type GymDetailsImage = {
  image_id: number
  image_url: string
  alt_text?: string | null
  display_order: number
}

export type GymDetailsLocation = {
  locality?: string | null
  city?: string | null
  state?: string | null
  country?: string | null
  full_address?: string | null
  latitude?: number | null
  longitude?: number | null
}

export type GymDetailsRatings = {
  average_rating?: number | null
  review_count: number
  user_rating?: number | null
}

export type GymDetailsOpeningHoursItem = {
  day_of_week: number
  open_time?: string | null
  close_time?: string | null
  is_closed: boolean
}

export type GymDetailsOpeningHours = {
  open_now?: boolean | null
  open_today?: string | null
  weekly: GymDetailsOpeningHoursItem[]
}

export type GymAmenity = {
  amenity_id: number
  amenity_name: string
  icon?: string | null
}

export type GymWorkoutOption = {
  workout_type_id: number
  workout_type_name: string
  icon?: string | null
  access_type: string
  additional_fee?: string | null
  membership_requirement?: string | null
}

export type GymMembershipAccess = {
  status:
    | 'INCLUDED'
    | 'UPGRADE_REQUIRED'
    | 'DAY_PASS_AVAILABLE'
    | 'NO_ACTIVE_MEMBERSHIP'
    | 'UNAVAILABLE'
    | string
  current_plan?: string | null
  required_plan?: string | null
  upgrade_required: boolean
  day_pass_available: boolean
  day_pass_price?: string | null
}

export type GymClassCard = {
  class_id: number
  kind: string
  status: string
  title: string
  gym_name: string
  start_at: string
  end_at: string
  level?: string | null
  filled: number
  capacity: number
}

export type RelatedGymItem = {
  gym_id: number
  gym_name: string
  primary_image?: string | null
  locality?: string | null
  city?: string | null
  distance_km?: number | null
  average_rating?: number | null
  review_count: number
  membership_access_status?: string | null
}

export type GymMemberReview = {
  review_id: number
  user_display_name: string
  rating: number
  comment?: string | null
  created_at: string
}

export type GymDetailsResponse = {
  gym_id: number
  gym_name: string
  slug: string
  location: GymDetailsLocation
  ratings: GymDetailsRatings
  images: GymDetailsImage[]
  opening_hours: GymDetailsOpeningHours
  workout_options: GymWorkoutOption[]
  amenities: GymAmenity[]
  description?: string | null
  important_information: string[]
  rules: string[]
  membership_access: GymMembershipAccess
  classes_nearby: GymClassCard[]
  related_gyms: RelatedGymItem[]
  reviews: GymMemberReview[]
  reviews_summary?: Record<string, unknown> | null
}

// Gym-level membership plans (single-gym subscriptions)
export type GymMembershipPlan = {
  id: number
  gym_id: number
  name: string
  description: string | null
  duration_days: number
  price: string
  currency: string
  is_active: boolean
}
