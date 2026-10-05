import type { OwnerGymDetails } from '../screens/GymOwner/api'

type Review = Pick<OwnerGymDetails, 'status' | 'rejection_reason' | 'can_submit_for_approval'>

export function canSubmitGym(gym: Review) {
  // Preserve draft submission on older deployments. Never infer resubmission permission.
  return gym.can_submit_for_approval ?? gym.status === 'DRAFT'
}

export function gymRejectionMessage(gym: Review) {
  const reason = gym.rejection_reason?.trim()
  return `This gym was rejected. ${reason ? `Reason: ${reason}` : 'No rejection reason was provided.'} ${canSubmitGym(gym) ? 'Update your gym details, then resubmit for approval.' : 'You can edit your gym details, but resubmission is not available yet.'}`
}