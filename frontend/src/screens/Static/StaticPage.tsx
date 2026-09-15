import styles from './staticPage.module.css'
import { navigate } from '../../router'
import ProfileIconButton from '../../components/ProfileIconButton'

type Props = {
  title: string
  description?: string
  backTo?: string
}

export default function StaticPage({ title, description, backTo = '/' }: Props) {
  return (
    <div className={styles.pageRoot}>
      <header className={styles.header}>
        <button type="button" className={styles.backBtn} onClick={() => navigate(backTo)}>
          ← Back
        </button>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true" />
          <span>GYMPASS</span>
        </div>

        <div className={styles.headerRight}>
          <ProfileIconButton className={styles.profileBtn} avatarClassName={styles.profileAvatar} />
        </div>
      </header>

      <main className={styles.main}>
        <div className={styles.card}>
          <h1 className={styles.title}>{title}</h1>
          {description ? <p className={styles.desc}>{description}</p> : null}
          <div className={styles.actions}>
            <button type="button" className={styles.primaryBtn} onClick={() => navigate('/nearby')}>
              Explore Nearby Gyms
            </button>
            <button type="button" className={styles.secondaryBtn} onClick={() => navigate('/')}
              aria-label="Go to home"
            >
              Home
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}
