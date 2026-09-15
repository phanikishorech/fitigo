import { useEffect, useMemo, useState } from 'react'
import OwnerLayout from './OwnerLayout'
import styles from './gymOwner.module.css'
import {
  bookingCancel,
  bookingMarkAttended,
  bookingMarkNoShow,
  createOwnerSlot,
  deactivateOwnerSlot,
  fetchFacilities,
  fetchGymDetailsOwner,
  listOwnerMembershipPlans,
  createOwnerMembershipPlan,
  updateOwnerMembershipPlan,
  deactivateOwnerMembershipPlan,
  activateOwnerMembershipPlan,
  inviteStaff,
  listBookings,
  listOwnerSlots,
  listStaff,
  removeStaff,
  setCoverImage,
  setGymFacilities,
  setOperatingHours,
  submitGymForApproval,
  updateGymOwner,
  updateOwnerSlot,
  uploadGymImage,
  type Facility,
  type OperatingHourItem,
  type OwnerBooking,
  type OwnerGymDetails,
  type OwnerMembershipPlan,
  type OwnerSlot,
  type StaffAssignment
} from './api'

const DOW = [
  { id: 0, label: 'Mon' },
  { id: 1, label: 'Tue' },
  { id: 2, label: 'Wed' },
  { id: 3, label: 'Thu' },
  { id: 4, label: 'Fri' },
  { id: 5, label: 'Sat' },
  { id: 6, label: 'Sun' }
]

type Tab = 'overview' | 'media' | 'facilities' | 'hours' | 'plans' | 'slots' | 'staff' | 'bookings'


export default function GymOwnerGymPage({ gymId }: { gymId: number }) {
  const [tab, setTab] = useState<Tab>('overview')

  const [gym, setGym] = useState<{ status: 'loading' } | { status: 'ready'; data: OwnerGymDetails } | { status: 'error'; message: string }>({
    status: 'loading'
  })
  const [facilities, setFacilities] = useState<{ status: 'loading' } | { status: 'ready'; data: Facility[] } | { status: 'error'; message: string }>({
    status: 'loading'
  })
  const [slots, setSlots] = useState<{ status: 'loading' } | { status: 'ready'; data: OwnerSlot[] } | { status: 'error'; message: string }>({
    status: 'loading'
  })
  const [plans, setPlans] = useState<{ status: 'loading' } | { status: 'ready'; data: OwnerMembershipPlan[] } | { status: 'error'; message: string }>({
    status: 'loading'
  })
  const [staff, setStaffState] = useState<{ status: 'loading' } | { status: 'ready'; data: StaffAssignment[] } | { status: 'error'; message: string }>({
    status: 'loading'
  })
  const [bookings, setBookings] = useState<{ status: 'loading' } | { status: 'ready'; data: OwnerBooking[] } | { status: 'error'; message: string }>({
    status: 'loading'
  })

  const title = useMemo(() => (gym.status === 'ready' ? gym.data.name : `Gym #${gymId}`), [gym.status, gymId])

  const existingClassNames = useMemo(() => {
    if (slots.status !== 'ready') return [] as string[]
    const s = new Set<string>()
    for (const it of slots.data) {
      const nm = String(it.name || '').trim()
      if (nm) s.add(nm)
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [slots])

  const reloadGym = () => {
    setGym({ status: 'loading' })
    fetchGymDetailsOwner(gymId)
      .then((d) => setGym({ status: 'ready', data: d }))
      .catch((e) => setGym({ status: 'error', message: e?.message ?? 'Failed to load gym' }))
  }

  const reloadAll = () => {
    reloadGym()
    setFacilities({ status: 'loading' })
    fetchFacilities()
      .then((d) => setFacilities({ status: 'ready', data: d }))
      .catch((e) => setFacilities({ status: 'error', message: e?.message ?? 'Failed to load facilities' }))

    setSlots({ status: 'loading' })
    listOwnerSlots(gymId)
      .then((d) => setSlots({ status: 'ready', data: d }))
      .catch((e) => setSlots({ status: 'error', message: e?.message ?? 'Failed to load slots' }))

    setPlans({ status: 'loading' })
    listOwnerMembershipPlans(gymId)
      .then((d) => setPlans({ status: 'ready', data: d }))
      .catch((e) => setPlans({ status: 'error', message: e?.message ?? 'Failed to load plans' }))

    setStaffState({ status: 'loading' })
    listStaff(gymId)
      .then((d) => setStaffState({ status: 'ready', data: d }))
      .catch((e) => setStaffState({ status: 'error', message: e?.message ?? 'Failed to load staff' }))

    setBookings({ status: 'loading' })
    listBookings(gymId)
      .then((d) => setBookings({ status: 'ready', data: d }))
      .catch((e) => setBookings({ status: 'error', message: e?.message ?? 'Failed to load bookings' }))
  }

  useEffect(() => {
    reloadAll()
  }, [gymId])

  const currentFacilityIds = gym.status === 'ready' ? new Set(gym.data.facilities.map((f) => f.id)) : new Set<number>()

  const [overviewForm, setOverviewForm] = useState({ name: '', city: '', description: '', phone: '', email: '', gym_price_per_person: '' })

  useEffect(() => {
    if (gym.status !== 'ready') return
    setOverviewForm({
      name: gym.data.name ?? '',
      city: gym.data.city ?? '',
      description: gym.data.description ?? '',
      phone: gym.data.phone ?? '',
      email: gym.data.email ?? '',
      gym_price_per_person: (gym.data.gym_price_per_person ?? '') as any
    })
  }, [gym.status])

  const operatingHours: OperatingHourItem[] = useMemo(() => {
    if (gym.status !== 'ready') return []
    const map = new Map<number, OperatingHourItem>()
    for (const it of gym.data.operating_hours ?? []) map.set(it.day_of_week, it)
    return DOW.map((d) =>
      map.get(d.id) ?? {
        day_of_week: d.id,
        open_time: '06:00:00',
        close_time: '22:00:00',
        is_closed: false
      }
    )
  }, [gym.status])

  const [hoursForm, setHoursForm] = useState<OperatingHourItem[]>([])
  useEffect(() => {
    setHoursForm(operatingHours)
  }, [operatingHours.length])

  const [invite, setInvite] = useState({ email: '', first_name: '', last_name: '' })
  const [slotForm, setSlotForm] = useState({
    name: '',
    start_time: '06:00:00',
    end_time: '07:00:00',
    capacity: 10,
    price: '99',
    class_mode: 'custom' as 'existing' | 'custom',
    is_occasional: false,
    specific_date: '',
    repeat_days: [] as number[]
  })

  const [planForm, setPlanForm] = useState({ name: '', duration_days: 30, price: '999.00', currency: 'INR', description: '' })
  const [planEdit, setPlanEdit] = useState<null | {
    id: number
    name: string
    duration_days: number
    price: string
    currency: string
    description: string
    is_active: boolean
  }>(null)

  return (
    <OwnerLayout title={title} active="gyms">
      {gym.status === 'error' ? <div className={styles.panel}>Error: {gym.message}</div> : null}
      <div className={styles.panel}>
        <div className={styles.row} style={{ justifyContent: 'space-between' }}>
          <div className={styles.row}>
            {(['overview', 'media', 'facilities', 'hours', 'plans', 'slots', 'staff', 'bookings'] as Tab[]).map((t) => (
              <button key={t} type="button" className={`${styles.navBtn} ${tab === t ? styles.navBtnActive : ''}`} onClick={() => setTab(t)}>
                {t}
              </button>
            ))}
          </div>
          <div className={styles.row}>
            <span className={styles.tag}>Gym ID: {gymId}</span>
            {gym.status === 'ready' ? <span className={styles.tag}>Status: {gym.data.status}</span> : null}
            <button type="button" className={styles.primaryBtn} onClick={reloadAll}>
              Refresh
            </button>
          </div>
        </div>
      </div>

      <div style={{ height: 12 }} />

      {tab === 'overview' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Gym details</div>
          {gym.status !== 'ready' ? (
            <div className={styles.subtle}>Loading…</div>
          ) : (
            <>
              <div className={styles.row}>
                <input className={styles.input} style={{ flex: 2, minWidth: 220 }} value={overviewForm.name} onChange={(e) => setOverviewForm((p) => ({ ...p, name: e.target.value }))} placeholder="Name" />
                <input className={styles.input} style={{ flex: 1, minWidth: 160 }} value={overviewForm.city} onChange={(e) => setOverviewForm((p) => ({ ...p, city: e.target.value }))} placeholder="City" />
              </div>
              <div style={{ height: 10 }} />
              <textarea className={styles.textarea} value={overviewForm.description} onChange={(e) => setOverviewForm((p) => ({ ...p, description: e.target.value }))} placeholder="Description" />
              <div style={{ height: 10 }} />
              <div className={styles.row}>
                <input className={styles.input} style={{ flex: 1, minWidth: 200 }} value={overviewForm.phone} onChange={(e) => setOverviewForm((p) => ({ ...p, phone: e.target.value }))} placeholder="Phone" />
                <input className={styles.input} style={{ flex: 2, minWidth: 220 }} value={overviewForm.email} onChange={(e) => setOverviewForm((p) => ({ ...p, email: e.target.value }))} placeholder="Email" />
              </div>
              <div style={{ height: 10 }} />
              <div className={styles.row}>
                <input
                  className={styles.input}
                  style={{ flex: 1, minWidth: 240 }}
                  value={overviewForm.gym_price_per_person}
                  onChange={(e) => setOverviewForm((p) => ({ ...p, gym_price_per_person: e.target.value }))}
                  placeholder="Gym price per person (₹)"
                  inputMode="decimal"
                />
              </div>
              <div style={{ height: 12 }} />
              <div className={styles.row}>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  onClick={async () => {
                    try {
                      await updateGymOwner(gymId, {
                        name: overviewForm.name,
                        city: overviewForm.city || null,
                        description: overviewForm.description || null,
                        phone: overviewForm.phone || null,
                        email: overviewForm.email || null,
                        gym_price_per_person: overviewForm.gym_price_per_person.trim() ? overviewForm.gym_price_per_person.trim() : '0.00'
                      } as any)
                      reloadGym()
                    } catch (e: any) {
                      alert(e?.message ?? 'Failed to save')
                    }
                  }}
                >
                  Save
                </button>
                {gym.data.status === 'DRAFT' ? (
                  <button
                    type="button"
                    className={styles.primaryBtn}
                    onClick={async () => {
                      try {
                        await submitGymForApproval(gymId)
                        reloadGym()
                        alert('Submitted for approval')
                      } catch (e: any) {
                        alert(e?.message ?? 'Failed to submit')
                      }
                    }}
                  >
                    Submit for approval
                  </button>
                ) : null}
              </div>
            </>
          )}
        </div>
      ) : null}

      {tab === 'media' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Gym images / cover</div>
          {gym.status !== 'ready' ? (
            <div className={styles.subtle}>Loading…</div>
          ) : (
            <>
              <div className={styles.row}>
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={async (e) => {
                    const f = e.target.files?.[0]
                    if (!f) return
                    try {
                      await uploadGymImage(gymId, f, false)
                      reloadGym()
                    } catch (err: any) {
                      alert(err?.message ?? 'Upload failed')
                    }
                  }}
                />
                <span className={styles.subtle}>Upload images. Then pick one as cover.</span>
              </div>
              <div style={{ height: 12 }} />
              <div className={styles.imgRow}>
                {gym.data.images.map((img) => (
                  <div key={img.id} className={styles.imgCard}>
                    <img src={`/uploads/${img.file_path}`} alt="" />
                    <div className={styles.imgCardFooter}>
                      <span className={styles.tag}>{img.is_cover ? 'COVER' : 'IMAGE'}</span>
                      {!img.is_cover ? (
                        <button
                          type="button"
                          className={styles.linkBtn}
                          onClick={async () => {
                            await setCoverImage(gymId, img.id)
                            reloadGym()
                          }}
                        >
                          Set cover
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
              {gym.data.images.length === 0 ? <div className={styles.subtle}>No images yet.</div> : null}
            </>
          )}
        </div>
      ) : null}

      {tab === 'facilities' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Facilities</div>
          {gym.status !== 'ready' || facilities.status !== 'ready' ? (
            <div className={styles.subtle}>Loading…</div>
          ) : (
            <>
              <div className={styles.subtle}>Select the facilities your gym provides.</div>
              <div style={{ height: 10 }} />
              <div className={styles.row}>
                {facilities.data.map((f) => {
                  const on = currentFacilityIds.has(f.id)
                  return (
                    <button
                      key={f.id}
                      type="button"
                      className={`${styles.navBtn} ${on ? styles.navBtnActive : ''}`}
                      onClick={() => {
                        const next = new Set(Array.from(currentFacilityIds))
                        if (on) next.delete(f.id)
                        else next.add(f.id)
                        // optimistic: update gym state locally
                        if (gym.status === 'ready') {
                          const nextFacilities = facilities.data.filter((ff) => next.has(ff.id))
                          setGym({ status: 'ready', data: { ...gym.data, facilities: nextFacilities } })
                        }
                      }}
                    >
                      {f.name}
                    </button>
                  )
                })}
              </div>
              <div style={{ height: 12 }} />
              <button
                type="button"
                className={styles.primaryBtn}
                onClick={async () => {
                  if (gym.status !== 'ready') return
                  try {
                    await setGymFacilities(gymId, gym.data.facilities.map((f) => f.id))
                    alert('Saved')
                  } catch (e: any) {
                    alert(e?.message ?? 'Failed')
                  }
                }}
              >
                Save facilities
              </button>
            </>
          )}
        </div>
      ) : null}

      {tab === 'hours' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Operating hours</div>
          {gym.status !== 'ready' ? (
            <div className={styles.subtle}>Loading…</div>
          ) : (
            <>
              {hoursForm.map((h) => (
                <div key={h.day_of_week} className={styles.row} style={{ marginBottom: 8 }}>
                  <span className={styles.tag} style={{ width: 64, justifyContent: 'center' }}>{DOW.find((d) => d.id === h.day_of_week)?.label ?? h.day_of_week}</span>
                  <label className={styles.subtle} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={h.is_closed}
                      onChange={(e) => {
                        setHoursForm((prev) => prev.map((x) => (x.day_of_week === h.day_of_week ? { ...x, is_closed: e.target.checked } : x)))
                      }}
                    />
                    Closed
                  </label>
                  <input
                    className={styles.input}
                    style={{ width: 160 }}
                    type="time"
                    disabled={h.is_closed}
                    value={(h.open_time ?? '06:00:00').slice(0, 5)}
                    onChange={(e) => {
                      const t = `${e.target.value}:00`
                      setHoursForm((prev) => prev.map((x) => (x.day_of_week === h.day_of_week ? { ...x, open_time: t } : x)))
                    }}
                  />
                  <input
                    className={styles.input}
                    style={{ width: 160 }}
                    type="time"
                    disabled={h.is_closed}
                    value={(h.close_time ?? '22:00:00').slice(0, 5)}
                    onChange={(e) => {
                      const t = `${e.target.value}:00`
                      setHoursForm((prev) => prev.map((x) => (x.day_of_week === h.day_of_week ? { ...x, close_time: t } : x)))
                    }}
                  />
                </div>
              ))}
              <div style={{ height: 10 }} />
              <button
                type="button"
                className={styles.primaryBtn}
                onClick={async () => {
                  try {
                    const payload = hoursForm.map((h) => ({
                      day_of_week: h.day_of_week,
                      is_closed: Boolean(h.is_closed),
                      open_time: h.is_closed ? null : h.open_time,
                      close_time: h.is_closed ? null : h.close_time
                    }))
                    await setOperatingHours(gymId, payload)
                    alert('Saved')
                    reloadGym()
                  } catch (e: any) {
                    alert(e?.message ?? 'Failed')
                  }
                }}
              >
                Save hours
              </button>
            </>
          )}
        </div>
      ) : null}

      {tab === 'plans' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Membership plans</div>
          {plans.status !== 'ready' ? (
            <div className={styles.subtle}>{plans.status === 'loading' ? 'Loading…' : (plans as any).message}</div>
          ) : (
            <>
              {plans.data.length === 0 ? <div className={styles.subtle}>No plans yet. Create one below.</div> : null}
              {plans.data.length > 0 ? (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Name</th>
                      <th>Duration</th>
                      <th>Price</th>
                      <th>Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plans.data.map((p) => (
                      <tr key={p.id}>
                        <td>{p.id}</td>
                        <td>{p.name}</td>
                        <td>{p.duration_days} days</td>
                        <td>
                          {p.currency} {p.price}
                        </td>
                        <td>{p.is_active ? 'ACTIVE' : 'INACTIVE'}</td>
                        <td>
                          <div className={styles.row}>
                            <button
                              type="button"
                              className={styles.secondaryBtn}
                              onClick={() =>
                                setPlanEdit({
                                  id: p.id,
                                  name: p.name,
                                  duration_days: p.duration_days,
                                  price: p.price,
                                  currency: p.currency,
                                  description: p.description ?? '',
                                  is_active: p.is_active
                                })
                              }
                            >
                              Edit
                            </button>
                            {p.is_active ? (
                              <button
                                type="button"
                                className={styles.dangerBtn}
                                onClick={async () => {
                                  if (!confirm('Deactivate this plan?')) return
                                  try {
                                    await deactivateOwnerMembershipPlan(p.id)
                                    setPlanEdit(null)
                                    reloadAll()
                                  } catch (e: any) {
                                    alert(e?.message ?? 'Failed to deactivate')
                                  }
                                }}
                              >
                                Deactivate
                              </button>
                            ) : (
                              <button
                                type="button"
                                className={styles.primaryBtn}
                                onClick={async () => {
                                  try {
                                    await activateOwnerMembershipPlan(p.id)
                                    reloadAll()
                                  } catch (e: any) {
                                    alert(e?.message ?? 'Failed to activate')
                                  }
                                }}
                              >
                                Activate
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}

              {planEdit ? (
                <>
                  <div style={{ height: 14 }} />
                  <div className={styles.panelTitle}>Edit plan #{planEdit.id}</div>
                  <div className={styles.row}>
                    <input className={styles.input} style={{ flex: 2, minWidth: 220 }} value={planEdit.name} onChange={(e) => setPlanEdit((p) => (p ? { ...p, name: e.target.value } : p))} placeholder="Name" />
                    <input
                      className={styles.input}
                      style={{ width: 150 }}
                      type="number"
                      min={1}
                      value={planEdit.duration_days}
                      onChange={(e) => setPlanEdit((p) => (p ? { ...p, duration_days: Number(e.target.value) } : p))}
                      placeholder="Days"
                    />
                    <input className={styles.input} style={{ width: 160 }} value={planEdit.price} onChange={(e) => setPlanEdit((p) => (p ? { ...p, price: e.target.value } : p))} placeholder="Price" />
                    <input className={styles.input} style={{ width: 110 }} value={planEdit.currency} onChange={(e) => setPlanEdit((p) => (p ? { ...p, currency: e.target.value } : p))} placeholder="Currency" />
                  </div>
                  <div style={{ height: 10 }} />
                  <textarea className={styles.textarea} value={planEdit.description} onChange={(e) => setPlanEdit((p) => (p ? { ...p, description: e.target.value } : p))} placeholder="Description (optional)" />
                  <div style={{ height: 10 }} />
                  <div className={styles.row}>
                    <button
                      type="button"
                      className={styles.primaryBtn}
                      onClick={async () => {
                        try {
                          await updateOwnerMembershipPlan(planEdit.id, {
                            name: planEdit.name,
                            duration_days: planEdit.duration_days,
                            price: planEdit.price,
                            currency: planEdit.currency,
                            description: planEdit.description.trim() ? planEdit.description.trim() : null
                          })
                          setPlanEdit(null)
                          reloadAll()
                        } catch (e: any) {
                          alert(e?.message ?? 'Failed to update')
                        }
                      }}
                    >
                      Save changes
                    </button>
                    <button type="button" className={styles.secondaryBtn} onClick={() => setPlanEdit(null)}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : null}

              <div style={{ height: 14 }} />
              <div className={styles.panelTitle}>Create plan</div>
              <div className={styles.row}>
                <input className={styles.input} style={{ flex: 2, minWidth: 220 }} value={planForm.name} onChange={(e) => setPlanForm((p) => ({ ...p, name: e.target.value }))} placeholder="Name (e.g. Monthly)" />
                <input
                  className={styles.input}
                  style={{ width: 150 }}
                  type="number"
                  min={1}
                  value={planForm.duration_days}
                  onChange={(e) => setPlanForm((p) => ({ ...p, duration_days: Number(e.target.value) }))}
                  placeholder="Days"
                />
                <input className={styles.input} style={{ width: 160 }} value={planForm.price} onChange={(e) => setPlanForm((p) => ({ ...p, price: e.target.value }))} placeholder="Price" />
                <input className={styles.input} style={{ width: 110 }} value={planForm.currency} onChange={(e) => setPlanForm((p) => ({ ...p, currency: e.target.value }))} placeholder="Currency" />
              </div>
              <div style={{ height: 10 }} />
              <textarea className={styles.textarea} value={planForm.description} onChange={(e) => setPlanForm((p) => ({ ...p, description: e.target.value }))} placeholder="Description (optional)" />
              <div style={{ height: 10 }} />
              <div className={styles.row}>
                <button
                  type="button"
                  className={styles.primaryBtn}
                  onClick={async () => {
                    try {
                      const nm = planForm.name.trim()
                      if (!nm) throw new Error('Name is required')
                      await createOwnerMembershipPlan(gymId, {
                        name: nm,
                        duration_days: Number(planForm.duration_days),
                        price: String(planForm.price).trim(),
                        currency: String(planForm.currency || 'INR').trim() || 'INR',
                        description: planForm.description.trim() ? planForm.description.trim() : null
                      })
                      setPlanForm({ name: '', duration_days: 30, price: '999.00', currency: 'INR', description: '' })
                      reloadAll()
                    } catch (e: any) {
                      alert(e?.message ?? 'Failed to create plan')
                    }
                  }}
                >
                  Create
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}

      {tab === 'slots' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Class slots</div>
          {slots.status !== 'ready' ? (
            <div className={styles.subtle}>Loading…</div>
          ) : (
            <>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Time</th>
                    <th>Capacity</th>
                    <th>Price</th>
                    <th>Active</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {slots.data.map((s) => (
                    <tr key={s.id}>
                      <td>{s.name}</td>
                      <td>
                        {String(s.start_time).slice(0, 5)}-{String(s.end_time).slice(0, 5)}
                      </td>
                      <td>{s.capacity}</td>
                      <td>{s.price}</td>
                      <td>{s.is_active ? 'Yes' : 'No'}</td>
                      <td>
                        <button
                          type="button"
                          className={styles.linkBtn}
                          onClick={async () => {
                            const name = prompt('Slot name', s.name) ?? s.name
                            const price = prompt('Price', s.price) ?? s.price
                            try {
                              await updateOwnerSlot(s.id, { name, price })
                              reloadAll()
                            } catch (e: any) {
                              alert(e?.message ?? 'Failed')
                            }
                          }}
                        >
                          Edit
                        </button>
                        {' · '}
                        <button
                          type="button"
                          className={styles.linkBtn}
                          onClick={async () => {
                            if (!confirm('Deactivate this slot?')) return
                            await deactivateOwnerSlot(s.id)
                            reloadAll()
                          }}
                        >
                          Deactivate
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ height: 14 }} />
              <div className={styles.panelTitle}>Create slot</div>
              <div className={styles.subtle} style={{ marginBottom: 10 }}>
                Slots are for classes only. Choose an existing class name or enter a custom class.
              </div>

              <div className={styles.row}>
                <select
                  className={styles.input}
                  style={{ flex: 2, minWidth: 220 }}
                  value={slotForm.class_mode}
                  onChange={(e) => {
                    const mode = e.target.value as 'existing' | 'custom'
                    setSlotForm((p) => ({
                      ...p,
                      class_mode: mode,
                      // keep name field but clear if switching to avoid accidental carry
                      name: mode === 'existing' ? (existingClassNames[0] ?? '') : ''
                    }))
                  }}
                >
                  <option value="existing">Select existing class</option>
                  <option value="custom">Custom class name</option>
                </select>

                {slotForm.class_mode === 'existing' ? (
                  <select
                    className={styles.input}
                    style={{ flex: 2, minWidth: 220 }}
                    value={slotForm.name}
                    onChange={(e) => setSlotForm((p) => ({ ...p, name: e.target.value }))}
                    disabled={existingClassNames.length === 0}
                  >
                    {existingClassNames.length === 0 ? <option value="">No classes yet</option> : null}
                    {existingClassNames.map((nm) => (
                      <option key={nm} value={nm}>
                        {nm}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className={styles.input}
                    style={{ flex: 2, minWidth: 220 }}
                    value={slotForm.name}
                    onChange={(e) => setSlotForm((p) => ({ ...p, name: e.target.value }))}
                    placeholder="Class name (e.g. Yoga)"
                  />
                )}
              </div>

              <div style={{ height: 10 }} />
              <div className={styles.row}>
                <input className={styles.input} style={{ width: 130 }} type="time" value={slotForm.start_time.slice(0, 5)} onChange={(e) => setSlotForm((p) => ({ ...p, start_time: `${e.target.value}:00` }))} />
                <input className={styles.input} style={{ width: 130 }} type="time" value={slotForm.end_time.slice(0, 5)} onChange={(e) => setSlotForm((p) => ({ ...p, end_time: `${e.target.value}:00` }))} />
                <input className={styles.input} style={{ width: 120 }} type="number" min={1} value={slotForm.capacity} onChange={(e) => setSlotForm((p) => ({ ...p, capacity: Number(e.target.value) }))} placeholder="Capacity" />
                <input className={styles.input} style={{ width: 140 }} value={slotForm.price} onChange={(e) => setSlotForm((p) => ({ ...p, price: e.target.value }))} placeholder="Price" />
              </div>

              <div style={{ height: 10 }} />
              <div className={styles.row}>
                <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontWeight: 750 }}>
                  <input
                    type="checkbox"
                    checked={slotForm.is_occasional}
                    onChange={(e) =>
                      setSlotForm((p) => ({
                        ...p,
                        is_occasional: e.target.checked,
                        specific_date: e.target.checked ? p.specific_date : '',
                        repeat_days: e.target.checked ? [] : p.repeat_days
                      }))
                    }
                  />
                  Specific date (occasional class)
                </label>

                {slotForm.is_occasional ? (
                  <input
                    className={styles.input}
                    style={{ width: 200 }}
                    type="date"
                    value={slotForm.specific_date}
                    onChange={(e) => setSlotForm((p) => ({ ...p, specific_date: e.target.value }))}
                  />
                ) : (
                  <div className={styles.row}>
                    <span className={styles.subtle} style={{ fontWeight: 750 }}>
                      Repeat on:
                    </span>
                    {DOW.map((d) => {
                      const on = slotForm.repeat_days.includes(d.id)
                      return (
                        <button
                          key={d.id}
                          type="button"
                          className={`${styles.navBtn} ${on ? styles.navBtnActive : ''}`}
                          onClick={() => {
                            setSlotForm((p) => {
                              const next = new Set(p.repeat_days)
                              if (next.has(d.id)) next.delete(d.id)
                              else next.add(d.id)
                              return { ...p, repeat_days: Array.from(next).sort((a, b) => a - b) }
                            })
                          }}
                        >
                          {d.label}
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>

              <div style={{ height: 12 }} />
              <button
                type="button"
                className={styles.primaryBtn}
                onClick={async () => {
                  try {
                    const name = slotForm.name.trim()
                    if (name.length < 2) throw new Error('Please enter a class name')

                    if (slotForm.is_occasional) {
                      if (!slotForm.specific_date) throw new Error('Please select a date')
                      await createOwnerSlot(gymId, {
                        name,
                        start_time: slotForm.start_time,
                        end_time: slotForm.end_time,
                        capacity: slotForm.capacity,
                        price: slotForm.price,
                        specific_date: slotForm.specific_date
                      })
                    } else {
                      if (!slotForm.repeat_days.length) throw new Error('Please select repeat days')
                      await createOwnerSlot(gymId, {
                        name,
                        start_time: slotForm.start_time,
                        end_time: slotForm.end_time,
                        capacity: slotForm.capacity,
                        price: slotForm.price,
                        repeat_days: slotForm.repeat_days
                      })
                    }

                    setSlotForm({
                      name: '',
                      start_time: '06:00:00',
                      end_time: '07:00:00',
                      capacity: 10,
                      price: '99',
                      class_mode: 'custom',
                      is_occasional: false,
                      specific_date: '',
                      repeat_days: []
                    })
                    reloadAll()
                  } catch (e: any) {
                    alert(e?.message ?? 'Failed')
                  }
                }}
              >
                Create class slot
              </button>
            </>
          )}
        </div>
      ) : null}

      {tab === 'staff' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Staff</div>
          {staff.status !== 'ready' ? (
            <div className={styles.subtle}>Loading…</div>
          ) : (
            <>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Assignment ID</th>
                    <th>User ID</th>
                    <th>Role</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {staff.data.map((s) => (
                    <tr key={s.id}>
                      <td>{s.id}</td>
                      <td>{s.user_id}</td>
                      <td>{s.role}</td>
                      <td>
                        <button
                          type="button"
                          className={styles.linkBtn}
                          onClick={async () => {
                            if (!confirm('Remove staff?')) return
                            await removeStaff(gymId, s.user_id)
                            reloadAll()
                          }}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ height: 14 }} />
              <div className={styles.panelTitle}>Invite staff</div>
              <div className={styles.row}>
                <input className={styles.input} style={{ flex: 2, minWidth: 220 }} placeholder="Email" value={invite.email} onChange={(e) => setInvite((p) => ({ ...p, email: e.target.value }))} />
                <input className={styles.input} style={{ flex: 1, minWidth: 140 }} placeholder="First" value={invite.first_name} onChange={(e) => setInvite((p) => ({ ...p, first_name: e.target.value }))} />
                <input className={styles.input} style={{ flex: 1, minWidth: 140 }} placeholder="Last" value={invite.last_name} onChange={(e) => setInvite((p) => ({ ...p, last_name: e.target.value }))} />
                <button
                  type="button"
                  className={styles.primaryBtn}
                  onClick={async () => {
                    try {
                      const res = await inviteStaff(gymId, {
                        email: invite.email.trim().toLowerCase(),
                        first_name: invite.first_name || null,
                        last_name: invite.last_name || null
                      })
                      if (res.temp_password) {
                        alert(`Staff created. Temporary password: ${res.temp_password}`)
                      } else {
                        alert('Staff invited/assigned')
                      }
                      setInvite({ email: '', first_name: '', last_name: '' })
                      reloadAll()
                    } catch (e: any) {
                      alert(e?.message ?? 'Failed')
                    }
                  }}
                >
                  Invite
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}

      {tab === 'bookings' ? (
        <div className={styles.panel}>
          <div className={styles.panelTitle}>Bookings</div>
          {bookings.status !== 'ready' ? (
            <div className={styles.subtle}>Loading…</div>
          ) : bookings.data.length === 0 ? (
            <div className={styles.subtle}>No bookings yet.</div>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Date</th>
                  <th>Slot</th>
                  <th>Customer</th>
                  <th>Status</th>
                  <th>Attendance</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {bookings.data.map((b) => (
                  <tr key={b.id}>
                    <td>{b.id}</td>
                    <td>{b.slot_date}</td>
                    <td>
                      {b.slot.name} ({String(b.slot.start_time).slice(0, 5)}-{String(b.slot.end_time).slice(0, 5)})
                    </td>
                    <td>{b.customer.email}</td>
                    <td>{b.status}</td>
                    <td>{b.attendance_status ?? '—'}</td>
                    <td>
                      <button
                        type="button"
                        className={styles.linkBtn}
                        onClick={async () => {
                          await bookingMarkAttended(b.id)
                          reloadAll()
                        }}
                      >
                        Attended
                      </button>
                      {' · '}
                      <button
                        type="button"
                        className={styles.linkBtn}
                        onClick={async () => {
                          await bookingMarkNoShow(b.id)
                          reloadAll()
                        }}
                      >
                        No-show
                      </button>
                      {' · '}
                      <button
                        type="button"
                        className={styles.linkBtn}
                        onClick={async () => {
                          if (!confirm('Cancel this booking?')) return
                          await bookingCancel(b.id, 'Owner cancelled')
                          reloadAll()
                        }}
                      >
                        Cancel
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </OwnerLayout>
  )
}
