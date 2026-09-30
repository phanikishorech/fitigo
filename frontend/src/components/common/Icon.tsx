const paths = {
  chart: 'M4 3v18h17 M8 16v-5 M13 16V7 M18 16V4',
  settings: 'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  bell: 'M18 8a6 6 0 0 0-12 0v6l-2 3h16l-2-3Z M10 21h4',
  help: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M9 8a3 3 0 0 1 6 0c0 2-3 2-3 5 M12 17h.01',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  plus: 'M12 5v14 M5 12h14',
  home: 'm3 10 9-7 9 7v10H3Z M9 20v-7h6v7',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  pin: 'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z M15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  arrow: 'M4 12h16 m-6-6 6 6-6 6',
  back: 'M20 12H4 m6-6-6 6 6 6',
  chevron: 'm9 5 7 7-7 7',
  down: 'm6 9 6 6 6-6',
  calendar: 'M4 5h16v16H4Z M8 2v6 M16 2v6 M4 11h16',
  qr: 'M3 3h6v6H3Z M15 3h6v6h-6Z M3 15h6v6H3Z M15 14v3h6v4h-6v-2 M21 12v2 M12 3v9H3 M12 15v6',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-2a8 8 0 0 1 16 0v2',
  wallet: 'M21 8H3V4h16v4 M3 8v13h18V8 M21 12h-6v5h6',
  heart: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z',
  gym: 'm6 6 12 12 M3 8l5-5 M16 21l5-5 M2 5l3-3 M19 22l3-3 M5 11l6-6 M13 19l6-6',
  check: 'm5 12 4 4L19 6',
  close: 'm6 6 12 12 M6 18 18 6',
  filter: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  star: 'm12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3L7.5 14 3 9.6l6.2-.9Z',
  clock: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M12 6v6l4 2',
  shield: 'm12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6Z m-5 10 3 3 5-6',
  ticket: 'M3 5h18v5a2 2 0 0 0 0 4v5H3v-5a2 2 0 0 0 0-4Z M15 5v3 m0 3v2 m0 3v3',
  spark: 'm12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z',
  logout: 'M9 4H3v16h6 M9 12h13 m-5-5 5 5-5 5',
  bag: 'M4 7h16l1 14H3Z M8 8V6a4 4 0 0 1 8 0v2',
  share: 'M12 15V2 m-5 5 5-5 5 5 M5 12H3v10h18V12h-2'
} as const
export type IconName = keyof typeof paths
export default function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}