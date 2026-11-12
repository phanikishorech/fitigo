import { useState } from 'react'
import { request } from '../services/client'
import { useMutation, useResource } from '../hooks/useResource'
import { Button, ConfirmDialog, ErrorState, Notice } from './UI'

type Job = { job_id: number; image_id: number; status: string; file_deleted: boolean; error_code: string | null }
export default function PhotoRemoval({ gymId, images, onSaved }: { gymId: number; images: { id: number; original_filename: string | null }[]; onSaved: () => void }) {
  const jobs = useResource(() => request<{ enabled: boolean; items: Job[] }>(`/gym-owner/gyms/${gymId}/image-deletions`, { cache: 'no-store' }), `photo-jobs:${gymId}:${images.map(i => i.id).join(',')}`)
  const mutation = useMutation(); const [selected, setSelected] = useState<number | null>(null); const [message, setMessage] = useState('')
  const done = (result: Job) => { setMessage(result.file_deleted ? 'Photo removed and stored file deleted.' : 'Photo removed from the gallery. Stored-file cleanup is pending or blocked; review the cleanup status below.'); setSelected(null); jobs.retry(); onSaved() }
  if (jobs.loading) return <Notice>Checking photo deletion availability…</Notice>
  if (jobs.error) return <ErrorState message={jobs.error} retry={jobs.retry} />
  if (!jobs.data?.enabled) return <Notice>Saved-photo deletion is disabled until the operational migration and configuration are deployed.</Notice>
  return <section className="ow-stack" aria-label="Photo removal">
    <Notice>Removal cannot be undone here. The cover is reassigned if needed. File cleanup may need retry; failed cleanup is never reported as completed.</Notice>
    {message && <p role="status">{message}</p>}{mutation.error && <Notice tone="error">{mutation.error}</Notice>}
    <div className="ow-actions">{images.map(image => <Button key={image.id} variant="danger" disabled={mutation.pending} onClick={() => { setMessage(''); setSelected(image.id) }}>Remove photo #{image.id}</Button>)}</div>
    {jobs.data.items.map(job => <article key={job.job_id}><p>Photo #{job.image_id}: {job.status} · {job.error_code || 'Cleanup awaiting retry'}</p><Button variant="secondary" disabled={mutation.pending} onClick={() => void mutation.run(async () => done(await request<Job>(`/gym-owner/gyms/${gymId}/image-deletions/${job.job_id}/retry`, { method: 'POST' })))}>Retry file cleanup</Button></article>)}
    {selected !== null && <ConfirmDialog title="Remove saved photo?" label="Remove photo" destructive pending={mutation.pending} error={mutation.error} onClose={() => { if (!mutation.pending) setSelected(null) }} onConfirm={() => void mutation.run(async () => done(await request<Job>(`/gym-owner/gyms/${gymId}/images/${selected}`, { method: 'DELETE' })))}>Remove photo #{selected} from this gym and request deletion of its stored file? Other gyms' photos are not affected.</ConfirmDialog>}
  </section>
}