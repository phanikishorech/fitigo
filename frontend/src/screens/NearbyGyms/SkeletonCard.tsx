import styles from './nearbyGyms.module.css'

export default function SkeletonCard() {
  return (
    <div className={`${styles.card} ${styles.skeleton}`} aria-hidden="true">
      <div className={styles.skelImage} />
      <div className={styles.cardBody}>
        <div className={styles.skelRow}>
          <div className={styles.skelTitle} />
          <div className={styles.skelRating} />
        </div>
        <div className={styles.skelMeta} />
        <div className={styles.skelIcons} />
        <div className={styles.skelPill} />
      </div>
    </div>
  )
}
