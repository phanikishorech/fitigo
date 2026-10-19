import OwnerApp from '../../owner/OwnerApp'

// Legacy URL uses the same gym selection, authorization and continuous scanner.
export default function StaffPage() {
  return <OwnerApp path="/owner/check-in" />
}