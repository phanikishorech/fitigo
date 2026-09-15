import styles from './nearbyGyms.module.css'
import type { GymDiscoverItem } from './types'
import { navigate } from '../../router'

function fmtDistance(km: number | null | undefined) {
  if (km == null) return ''
  if (km < 1) return `${Math.round(km * 1000)} m`
  return `${km.toFixed(km < 10 ? 1 : 0)} km`
}

function badgeForAccess(status: GymDiscoverItem['membership_access_status']) {
  switch (status) {
    case 'INCLUDED':
      return { label: 'Included', tone: 'brand' as const }
    case 'UPGRADE_REQUIRED':
      return { label: 'Upgrade Required', tone: 'warn' as const }
    case 'DAY_PASS_AVAILABLE':
      return { label: 'Day Pass Available', tone: 'neutral' as const }
    case 'NO_ACTIVE_MEMBERSHIP':
      return { label: 'View Membership Plans', tone: 'neutral' as const }
    case 'UNAVAILABLE':
      return { label: 'Currently Unavailable', tone: 'muted' as const }
    default:
      return { label: status ? String(status) : 'Access', tone: 'neutral' as const }
  }
}

export default function GymCard({ gym }: { gym: GymDiscoverItem }) {
  const access = badgeForAccess(gym.membership_access_status)
  const facs = gym.facilities ?? []
  const mainIcons = facs.slice(0, 2)
  const more = Math.max(0, facs.length - mainIcons.length)

  return (
    <a
      className={styles.card}
      href={`/gyms/${gym.gym_id}`}
      aria-label={`View ${gym.gym_name}`}
      onClick={(e) => {
        // SPA navigation when possible
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
        e.preventDefault()
        navigate(`/gyms/${gym.gym_id}`)
      }}
    >
      <div className={styles.cardImageWrap}>
        {gym.primary_image ? (
          <img className={styles.cardImage} src={gym.primary_image} alt={gym.gym_name} loading="lazy" />
        ) : (
          <div className={styles.cardImagePlaceholder} aria-hidden="true" />
        )}

        {gym.is_featured ? <div className={styles.badgeFeatured}>Featured</div> : null}
        <div
          className={`${styles.badgeAccess} ${
            access.tone === 'brand'
              ? styles.badgeAccessBrand
              : access.tone === 'warn'
                ? styles.badgeAccessWarn
                : access.tone === 'muted'
                  ? styles.badgeAccessMuted
                  : styles.badgeAccessNeutral
          }`}
        >
          {access.label}
        </div>
      </div>

      <div className={styles.cardBody}>
        <div className={styles.cardTopRow}>
          <div className={styles.cardTitle} title={gym.gym_name}>
            {gym.gym_name}
          </div>
          <div className={styles.cardRating}>
            {gym.average_rating != null ? (
              <>
                <span className={styles.star} aria-hidden="true">
                  ★
                </span>
                <span style={{ fontWeight: 650 }}>{gym.average_rating.toFixed(2)}</span>
                <span className={styles.cardReviews}>({gym.review_count})</span>
              </>
            ) : (
              <span className={styles.cardNew}>New</span>
            )}
          </div>
        </div>

        <div className={styles.cardMeta}>
          {[gym.locality || gym.address || gym.city || 'Nearby', gym.distance_km != null ? fmtDistance(gym.distance_km) : null]
            .filter(Boolean)
            .join(' · ')}
        </div>

        <div className={styles.facRow}>
          {mainIcons.map((f) => (
            <span key={f.id} className={styles.facIcon} title={f.name} aria-label={f.name}>
              {f.icon ? f.icon : '⬤'}
            </span>
          ))}
          {more ? (
            <span className={styles.facMore}>
              + {more} more
            </span>
          ) : null}
        </div>

        {gym.active_promotion ? <div className={styles.promoPill}>{gym.active_promotion}</div> : null}
      </div>
    </a>
  )
}
