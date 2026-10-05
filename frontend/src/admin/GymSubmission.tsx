import type { AdminGymDetails } from './services'
import { dateLabel, money } from '../services/client'
import { Alert, DataCard, Details, Icon, ImageGallery, StatusBadge } from './UI'

const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export default function GymSubmission({ gym }: { gym: AdminGymDetails }) {
  return <>
    <DataCard title="Submitted photos"><ImageGallery name={gym.name} images={gym.images.map(image => ({ src: `/uploads/${image.file_path}`, alt: image.original_filename || gym.name }))} /></DataCard>
    <DataCard title="About this gym"><p className="ad-description">{gym.description || 'No description submitted.'}</p><Details rows={[["Gym phone", gym.phone], ['Gym email', gym.email], ['Last updated', dateLabel(gym.updated_at)]]} /></DataCard>
    <div className="ad-detail-grid">
      <DataCard title="Location"><Details rows={[["Address", [gym.address_line_1, gym.address_line_2].filter(Boolean).join(', ')], ['City', gym.city], ['State', gym.state], ['Postal code', gym.postal_code], ['Country', gym.country], ['Latitude', gym.latitude], ['Longitude', gym.longitude]]} /></DataCard>
      <DataCard title="Operating hours"><Details rows={days.map((day, index) => {
        const hours = gym.operating_hours.find(item => item.day_of_week === index)
        return [day, !hours ? 'Not submitted' : hours.is_closed ? 'Closed' : `${hours.open_time?.slice(0, 5) || 'Not submitted'} – ${hours.close_time?.slice(0, 5) || 'Not submitted'}`]
      })} /></DataCard>
    </div>
    <div className="ad-detail-grid">
      <DataCard title="Facilities">{gym.facilities.length ? <div className="ad-facilities">{gym.facilities.map(facility => <span key={facility.id} title={facility.description || undefined}><Icon name="check" size={17} />{facility.name}</span>)}</div> : <p>No facilities submitted.</p>}</DataCard>
      <DataCard title="Pricing"><Details rows={[["Day pass · per person", gym.gym_price_per_person === undefined ? 'Not submitted' : money(gym.gym_price_per_person)], ['Classes offered', gym.has_classes ? 'Yes' : 'No']]} /></DataCard>
    </div>
    {gym.status === 'REJECTED' && <DataCard title="Rejection reason"><Alert tone="danger">This gym is rejected. {gym.rejection_reason || 'No rejection reason was recorded.'}</Alert></DataCard>}
    {gym.review_history.length > 0 && <DataCard title="Review history"><Details rows={gym.review_history.map(item => [`${dateLabel(item.created_at)} · #${item.id}`, <><StatusBadge status={item.new_status} /><p className="ad-description">{item.reason || `Status changed from ${item.old_status.replaceAll('_', ' ').toLowerCase()}.`}</p></>])} /></DataCard>}
  </>
}