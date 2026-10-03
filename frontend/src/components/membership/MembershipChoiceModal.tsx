import { useId } from 'react'
import { Button, Modal } from '../common/UI'

export default function MembershipChoiceModal({ onMembership, onOthers, onClose }: { onMembership: () => void; onOthers: () => void; onClose: () => void }) {
  const description = useId()
  return <Modal title="You have an active membership" onClose={onClose} showCloseButton={false} className="fg-membership-choice" describedBy={description}>
    <p id={description} className="fg-muted">Choose how you want to continue.</p>
    <div className="fg-membership-choice-actions">
      <Button onClick={onMembership}>Use My Membership</Button>
      <Button variant="secondary" onClick={onOthers}>Book for Others</Button>
    </div>
  </Modal>
}