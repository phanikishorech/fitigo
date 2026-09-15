export function maskEmail(email: string): string {
  const e = email.trim()
  const at = e.indexOf('@')
  if (at <= 1) return e
  const local = e.slice(0, at)
  const domain = e.slice(at + 1)
  const localMasked = local.slice(0, 2) + '****'
  const domainParts = domain.split('.')
  if (domainParts.length < 2) return `${localMasked}@${domain}`
  const d0 = domainParts[0]
  const rest = domainParts.slice(1).join('.')
  const d0Masked = d0.length <= 2 ? d0[0] + '***' : d0.slice(0, 1) + '***' + d0.slice(-1)
  return `${localMasked}@${d0Masked}.${rest}`
}
