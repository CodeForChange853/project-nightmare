// Tiny inline icon set (24px grid, stroke-based) so the UI ships with no icon library.
const PATHS = {
  folder: 'M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z',
  bell: 'M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 1.5h-15zM10 20.5a2 2 0 0 0 4 0',
  app: 'M4.5 4.5h6v6h-6zM13.5 4.5h6v6h-6zM4.5 13.5h6v6h-6zM13.5 13.5h6v6h-6z',
  bolt: 'M13 3 5 13.5h6L10 21l8-10.5h-6z',
  spark: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18',
  mic: 'M12 3.5a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0v-5a3 3 0 0 1 3-3zM5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3',
  send: 'M4 12 20 4l-4 16-4-6.5zM12 13.5 20 4',
  lock: 'M6.5 10.5h11v9h-11zM8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5',
  voice: 'M4 9.5v5h3.5L12 18.5v-13L7.5 9.5zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11',
  mute: 'M4 9.5v5h3.5L12 18.5v-13L7.5 9.5zM16 9.5l5 5M21 9.5l-5 5',
  globe: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM3.5 12h17M12 3.5c2.5 2.6 3.5 5.4 3.5 8.5s-1 5.9-3.5 8.5c-2.5-2.6-3.5-5.4-3.5-8.5s1-5.9 3.5-8.5z',
  check: 'M5 12.5 10 17.5 19 7',
  branch: 'M7 4.5v15M7 15.5a4 4 0 0 0 4-4h2a4 4 0 0 0 4-4V4.5M17 4.5a1.5 1.5 0 1 1 0 .01M7 19.5a1.5 1.5 0 1 1 0 .01',
  chevron: 'M9.5 6l6 6-6 6',
  refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4',
  warn: 'M12 4 21 19.5H3zM12 10v4.5M12 17.2v.3',
  log: 'M5 6.5h14M5 11h14M5 15.5h9',
  database:
    'M4.5 6.5c0-1.7 3.4-3 7.5-3s7.5 1.3 7.5 3-3.4 3-7.5 3-7.5-1.3-7.5-3zM4.5 6.5v11c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-11M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3',
  external: 'M14 4.5h5.5V10M19.5 4.5 11 13M17 13.5V19a.5.5 0 0 1-.5.5h-11A.5.5 0 0 1 5 19V8a.5.5 0 0 1 .5-.5H11',
  trash: 'M5 7h14M10 7V4.5h4V7M7 7l1 12.5h8L17 7M10.5 11v5M13.5 11v5',
  close: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  eye:'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6z',
}

export default function Icon({ name, size = 16, className = '', strokeWidth = 1.6 }) {
  return (
    <svg
      aria-hidden
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d={PATHS[name]} />
    </svg>
  )
}

/** The Nightmare sigil: a blood moon cut by a slit pupil. */
export function Sigil({ size = 28, className = '' }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 32 32" className={className}>
      <defs>
        <radialGradient id="sigil-moon" cx="38%" cy="32%" r="75%">
          <stop offset="0" stopColor="#ff8a95" />
          <stop offset="0.45" stopColor="#dc143c" />
          <stop offset="1" stopColor="#3a0610" />
        </radialGradient>
      </defs>
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="#5c1a24" strokeWidth="1" />
      <circle cx="16" cy="16" r="10" fill="url(#sigil-moon)" />
      <path d="M16 7.5c2.2 2.6 2.2 14.4 0 17-2.2-2.6-2.2-14.4 0-17z" fill="#070203" />
    </svg>
  )
}
