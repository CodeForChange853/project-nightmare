// Calls go to /api/* (proxied in Vite dev mode, or served directly by FastAPI in production mode).

export class AuthError extends Error {
  constructor(message) {
    super(message)
    this.name = 'AuthError'
  }
}

export const translateMeeting = (text, signal) => call('/meeting/translate', {
  method: 'POST', body: JSON.stringify({ text }), signal,
})

async function call(path, options = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    })
  } catch {
    if (options.signal?.aborted) throw new DOMException('Cancelled', 'AbortError')
    throw new Error('Cannot reach the backend. Is `python -m backend` running?')
  }
  if (res.status === 401) {
    let detail = 'PIN required to unlock Nightmare.'
    try {
      const data = await res.json()
      if (data?.detail) detail = data.detail
    } catch {
      /* ignore */
    }
    throw new AuthError(detail)
  }
  if (res.status === 429) {
    let message = 'Too many requests. Try again shortly.'
    try { message = (await res.json()).detail || message } catch { /* no JSON */ }
    throw new Error(message)
  }
  if (res.status === 403) {
    let detail = 'Backend refused the request (origin/host or read-only session).'
    try {
      const data = await res.json()
      if (data?.detail) detail = data.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.status === 502 || res.status === 504) {
    throw new Error('Backend is not answering. Is `python -m backend` running?')
  }
  if (!res.ok) {
    // 409 / 422 from Settings carry {message, errors: [...]} or a plain string
    let detail
    try {
      detail = (await res.json())?.detail
    } catch {
      /* ignore */
    }
    const err = new Error(
      typeof detail === 'string' ? detail : detail?.message || `Backend error ${res.status}`,
    )
    err.status = res.status
    err.errors = Array.isArray(detail?.errors) ? detail.errors : []
    throw err
  }
  return res.json()
}

export const getStatus = () => call('/status')

export const sendChat = (text) => call('/chat', { method: 'POST', body: JSON.stringify({ text }) })

export const confirmAction = (id, approve) =>
  call('/confirm', { method: 'POST', body: JSON.stringify({ id, approve }) })

export const loginPin = (pin) => call('/login', { method: 'POST', body: JSON.stringify({ pin }) })

export const logoutSession = () => call('/logout', { method: 'POST' })

export const getHelp = () => call('/help')

export const resetSession = () => call('/session/reset', { method: 'POST' })

export const getRouterReview = () => call('/router/review')

export const approveRouterMiss = (miss_id, approved_intent) =>
  call('/router/approve', { method: 'POST', body: JSON.stringify({ miss_id, approved_intent }) })

// Database viewer: the PIN buys a short-lived token that lives only in React state.
const dbHeaders = (token) => ({ 'X-DB-Token': token })

export const openDb = (pin) => call('/db/open', { method: 'POST', body: JSON.stringify({ pin }) })

export const closeDb = (token) => call('/db/close', { method: 'POST', headers: dbHeaders(token) })

export const getDbRecords = (token) => call('/db/records', { headers: dbHeaders(token) })

export const getDbActions = (token, { group = '', outcome = '', q = '', before } = {}) => {
  const params = new URLSearchParams({ group, outcome, q })
  if (before != null) params.set('before', before)
  return call(`/db/actions?${params}`, { headers: dbHeaders(token) })
}

export const deleteDbNote = (token, id) =>
  call(`/db/notes/${encodeURIComponent(id)}/delete`, { method: 'POST', headers: dbHeaders(token) })

export const deleteDbFact = (token, id) =>
  call(`/db/facts/${encodeURIComponent(id)}/delete`, { method: 'POST', headers: dbHeaders(token) })

export const deleteDbCalendarEvent = (token, id) =>
  call(`/db/calendar/${encodeURIComponent(id)}/delete`, { method: 'POST', headers: dbHeaders(token) })

export const deleteDbMeasurableTask = (token, id) =>
  call(`/db/tasks/${encodeURIComponent(id)}/delete`, { method: 'POST', headers: dbHeaders(token) })

// Settings (apps.json): same idea as the database, its own PIN-bought token
const settingsHeaders = (token) => ({ 'X-Settings-Token': token })

export const openSettings = (pin) => call('/settings/open', { method: 'POST', body: JSON.stringify({ pin }) })

export const closeSettings = (token) => call('/settings/close', { method: 'POST', headers: settingsHeaders(token) })

export const getAppsConfig = (token) => call('/settings/apps', { headers: settingsHeaders(token) })

export const saveAppsConfig = (token, body) =>
  call('/settings/apps', { method: 'POST', headers: settingsHeaders(token), body: JSON.stringify(body) })

export const checkAppsEntry = (token, kind, spec) =>
  call('/settings/apps/check', { method: 'POST', headers: settingsHeaders(token), body: JSON.stringify({ kind, spec }) })

// Security Clearance (Level 5 Architect Single-Tier)
export const getClearanceStatus = () => call('/clearance/status')

// Shared Drive Timeline & Team Quotas (Phase 8D)
export const getTeamProgress = (team = '') => {
  const q = team ? `?team=${encodeURIComponent(team)}` : ''
  return call(`/team-tracker/progress${q}`)
}

export const sendTeamNudge = (taskId) =>
  call('/team-tracker/nudge', { method: 'POST', body: JSON.stringify({ task_id: taskId }) })

export const getTimelineDiff = () => call('/team-tracker/diff')

export const syncTimelineBaseline = () => call('/team-tracker/sync', { method: 'POST' })

export const openTimelineInExcel = () => call('/team-tracker/open-excel', { method: 'POST' })

// Priority Push Notifications (Real-Time Pub/Sub Email Feed)
export const getPriorityEmails = (limit = 50, status = '', category = '') => {
  const params = new URLSearchParams()
  if (limit) params.set('limit', limit)
  if (status) params.set('status', status)
  if (category) params.set('category', category)
  const q = params.toString() ? `?${params.toString()}` : ''
  return call(`/emails/priority${q}`)
}

export const updateEmailStatus = (id, status = 'Read') =>
  call(`/emails/${encodeURIComponent(id)}/status`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  })

// Local Calendar & Measurable Tasks
export const getCalendarEvents = (start = '', end = '') => {
  const params = new URLSearchParams()
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  const q = params.toString() ? `?${params.toString()}` : ''
  return call(`/calendar/events${q}`)
}

export const createCalendarEvent = (data) =>
  call('/calendar/events', { method: 'POST', body: JSON.stringify(data) })

export const getMeasurableTasks = () => call('/tasks/measurable')

export const updateMeasurableTask = (data) =>
  call('/tasks/measurable', { method: 'POST', body: JSON.stringify(data) })

// Phase 8F Thesis Defense & Phase 9A Hardware Telemetry
export const getDefenseSessions = (limit = 10) => call(`/defense/sessions?limit=${limit}`)
export const getDefenseStatus = () => call('/defense/status')
export const getHardwareTelemetry = () => call('/system/telemetry')
export const getLiveWeather = (city = '', force = false) => {
  const params = new URLSearchParams()
  if (city) params.set('city', city)
  if (force) params.set('force', 'true')
  const q = params.toString() ? `?${params.toString()}` : ''
  return call(`/weather${q}`)
}
export const setWindowMode = (mode) =>
  call('/window/mode', { method: 'POST', body: JSON.stringify({ mode }) })


