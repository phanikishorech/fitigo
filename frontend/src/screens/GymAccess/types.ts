export type MembershipStatusBanner = {
  status: string
  title: string
  subtitle?: string | null
  tone: 'success' | 'warn' | 'info' | string
}

export type AccessTypeOption = {
  id: string
  name: string
  type: string
  icon?: string | null
  membership_included: boolean
  additional_price?: string | null
}

export type GymBookingOptionsResponse = {
  gym_id: number
  gym_name: string
  locality?: string | null
  city?: string | null
  membership_status: MembershipStatusBanner
  available_access_types: AccessTypeOption[]
  workout_areas: { id: string; name: string }[]

  // New Add-to-Cart booking model fields (backend adds these in booking-options response)
  gym_price_per_person?: string
  has_classes?: boolean
  classes_available?: boolean
  classes_unavailable_message?: string | null
}

export type OperatingHoursForDateResponse = {
  gym_id: number
  date: string
  day_of_week: number
  open_time?: string | null
  close_time?: string | null
  is_closed: boolean
  label?: string | null
}

export type ClassSessionPublicResponse = {
  id: number
  gym_id: number
  class_id: number
  class_name: string
  class_date: string
  start_time: string
  end_time: string
  maximum_capacity: number
  booked_capacity: number
  available_capacity: number
  price_per_person: string
  status: string
}

export type CartItemCreateGymRequest = {
  booking_type: 'GYM'
  gym_id: number
  booking_date: string
  preferred_start_time: string
  preferred_end_time: string
  member_count: number
}

export type CartItemCreateClassRequest = {
  booking_type: 'CLASS'
  gym_id: number
  class_session_id: number
  booking_date: string
  member_count: number
}

export type CartItemResponse = {
  id: number
  booking_type: string
  gym_id: number
  class_session_id?: number | null
  booking_date: string
  preferred_start_time?: string | null
  preferred_end_time?: string | null
  member_count: number
  price_per_person: string
  total_price: string
  currency: string
  status: string
  gym_name?: string | null
  class_name?: string | null
  start_time?: string | null
  end_time?: string | null
  available_capacity?: number | null
}

export type ListCartItemsResponse = CartItemResponse[]

export type CartCheckoutResponse = {
  confirmed_items: CartItemResponse[]
  total_amount: string
  currency: string
}

export type ValidateBookingRequest = {
  access_type_id: string
  gym_slot_id: number
  slot_date: string
  quantity: number
  duration_minutes?: number | null
  workout_area_id?: string | null
  resource_id?: string | null
}

export type ValidateBookingResponse = {
  available: boolean
  availability_message: string
  membership_eligible: boolean
  currency: string
  price: string
  discount: string
  tax: string
  total: string
}

export type CreateAccessBookingRequest = {
  items: ValidateBookingRequest[]
  notes?: string | null
}

export type CreateAccessBookingResponse = {
  results: {
    booking_id: number
    status: string
    payment_status?: string | null
    total: string
    currency: string
  }[]
}
