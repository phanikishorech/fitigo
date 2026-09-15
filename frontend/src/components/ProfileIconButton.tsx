import { navigate } from '../router'
import { getAccessToken } from '../auth'
import { openAuthModal } from '../authUi'

export default function ProfileIconButton({
  className,
  avatarClassName,
  ariaLabel = 'Open profile'
}: {
  className: string
  avatarClassName: string
  ariaLabel?: string
}) {
  return (
    <button
      type="button"
      className={className}
      onClick={() => {
        const token = getAccessToken()
        if (!token) {
          openAuthModal('profile_button')
          return
        }
        navigate('/profile')
      }}
      aria-label={ariaLabel}
    >
      <span className={avatarClassName} aria-hidden="true" />
    </button>
  )
}
