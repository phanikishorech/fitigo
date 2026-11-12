import type { AuthResult, AuthTokens } from '../components/AuthModal/AuthModal'
import { ApiError, post, request } from './client'
export const authService = {
  registerCustomer: (body: { first_name: string; last_name: string; email: string; phone: string | null; password: string }) => post<{ id: number; email: string }>('/auth/register/customer', { ...body, email: body.email.trim().toLowerCase() }),
  resetOptions: () => request<{ email_available: boolean; expiry_minutes: number }>('/auth/password-reset/options', { cache: 'no-store' }),
  otpOptions: () => request<{ email_available: boolean; mobile_available: boolean; expiry_seconds: number; resend_seconds: number }>('/auth/otp/options', { cache: 'no-store' }),
  inspectInvitation: (token: string) => post<{ gym_name: string; expires_at: string; requires_current_password: boolean }>('/auth/staff-invitations/inspect', { token }),
  acceptInvitation: (token: string, password: string, existing: boolean) => post('/auth/staff-invitations/accept', { token, [existing ? 'current_password' : 'new_password']: password }),
  forgotPassword: (email: string) => post<{ message: string }>('/auth/forgot-password', { email: email.trim().toLowerCase() }),
  resetPassword: (token: string, newPassword: string) => post('/auth/reset-password', { token, new_password: newPassword }),
  changePassword: (currentPassword: string, newPassword: string) => post('/auth/change-password', { current_password: currentPassword, new_password: newPassword }),
  loginWithPassword: async (email: string, password: string): Promise<AuthTokens> => {
    try {
      return await post<AuthTokens>('/auth/login', { email: email.trim().toLowerCase(), password })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) throw new ApiError('The email or password is incorrect. Please try again.', 401)
      throw error
    }
  },
  sendEmail: (email: string) => post<{ resend_seconds: number }>('/auth/email/send-otp', { email }),
  verifyEmail: (email: string, otp: string) => post<AuthResult>('/auth/email/verify-otp', { email, otp }),
  sendMobile: (countryCode: string, number: string) => post<{ resend_seconds: number }>('/auth/mobile/send-otp', { country_code: countryCode, mobile_number: number }),
  verifyMobile: (countryCode: string, number: string, otp: string) => post<AuthResult>('/auth/mobile/verify-otp', { country_code: countryCode, mobile_number: number, otp })
}