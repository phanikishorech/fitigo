import type { AuthResult, AuthTokens } from '../components/AuthModal/AuthModal'
import { ApiError, post } from './client'
export const authService = {
  loginWithPassword: async (email: string, password: string): Promise<AuthTokens> => {
    try {
      return await post<AuthTokens>('/auth/login', { email: email.trim().toLowerCase(), password })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) throw new ApiError('The email or password is incorrect. Please try again.', 401)
      throw error
    }
  },
  sendEmail: (email: string) => post<unknown>('/auth/email/send-otp', { email }),
  verifyEmail: (email: string, otp: string) => post<AuthResult>('/auth/email/verify-otp', { email, otp }),
  sendMobile: (countryCode: string, number: string) => post<unknown>('/auth/mobile/send-otp', { country_code: countryCode, mobile_number: number }),
  verifyMobile: (countryCode: string, number: string, otp: string) => post<AuthResult>('/auth/mobile/verify-otp', { country_code: countryCode, mobile_number: number, otp })
}