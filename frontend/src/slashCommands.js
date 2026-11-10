// Typed-only shortcuts. They are handled in the browser (App.jsx); voice can't produce "/".
export const SLASH_COMMANDS = [
  { name: '/voice', hint: 'Choose and preview a free browser voice' },
  { name: '/meeting', hint: 'Live Mandarin captions with English translation · mic or PC audio' },
  { name: '/transcribe', hint: 'Open live meeting captions' },
  { name: '/help', hint: 'Show every command Nightmare understands' },
  { name: '/emails', hint: 'Open real-time priority email push feed' },
  { name: '/timeline', hint: 'Open thesis timeline & team progress telemetry' },
  { name: '/defense', hint: 'Open academic thesis defense co-pilot panel' },
  { name: '/telemetry', hint: 'Inspect system hardware telemetry (CPU, RAM, battery)' },
  { name: '/review', hint: 'Review router miss queue and approve custom exemplars' },
  { name: '/clear', hint: 'Clear the conversation and start a new session' },
  { name: '/new', hint: 'Start a new session (same as /clear)' },
  { name: '/reminders', hint: 'Read your reminders' },
  { name: '/db', hint: 'Open the database and audit viewer' },
  { name: '/settings', hint: 'Edit the apps and tasks Nightmare may open or run' },
  { name: '/sleep', hint: 'Put Nightmare to sleep until you say “Nightmare, wake up”' },
]
