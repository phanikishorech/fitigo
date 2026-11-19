import { businessService } from './businessService'
import { useAdminResource } from './hooks'
import { DataCard, Details, Resource } from './UI'
import { istDateTime } from '../utils/membership'
export default function BookingAttendance({ id }: { id: number }) {
  const resource = useAdminResource(() => businessService.attendance(id), `admin-booking-attendance:${id}`)
  return <DataCard title="Check-in status"><Resource resource={resource}>{data => <Details rows={[["Verified visitors", `${data.completed_visitors} of ${data.purchased_visitors}`], ['No-show', data.no_show ? 'Confirmed no-show' : 'Not marked as a no-show'], ['Marked at', data.marked_at ? istDateTime(data.marked_at) : 'Not marked']]} />}</Resource></DataCard>
}