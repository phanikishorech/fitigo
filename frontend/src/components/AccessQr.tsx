import { useMemo } from 'react'
import { accessQrMatrix } from './accessQrMatrix'

export default function AccessQr({ token }: { token: string }) {
  const path = useMemo(() => accessQrMatrix(token).flatMap((row, y) =>
    row.flatMap((dark, x) => dark ? [`M${x + 4},${y + 4}h1v1h-1z`] : [])
  ).join(''), [token])
  return <svg role="img" aria-label="Today's one-time gym access QR" viewBox="0 0 41 41" width="246" height="246" style={{ maxWidth: '100%', height: 'auto' }} shapeRendering="crispEdges">
    <rect width="41" height="41" fill="white" />
    <path d={path} fill="black" />
  </svg>
}