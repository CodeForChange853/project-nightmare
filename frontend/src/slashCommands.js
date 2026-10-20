// Typed-only shortcuts. They are handled in the browser (App.jsx); voice can't produce "/".
export const SLASH_COMMANDS = [
  { name: '/help', hint: 'Show every command Nightmare understands' },
  { name: '/clear', hint: 'Clear the conversation and start a new session' },
  { name: '/new', hint: 'Start a new session (same as /clear)' },
  { name: '/reminders', hint: 'Read your reminders' },
  { name: '/db', hint: 'Open the database (asks for your PIN)' },
  { name: '/sleep', hint: 'Put Nightmare to sleep until you say “Nightmare, wake up”' },
]
