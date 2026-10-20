// Calls go to /api/* (proxied in Vite dev mode, or served directly by FastAPI in production mode).

export class AuthError extends Error {
  constructor(message) {
    super(message)
    this.name = 'AuthError'
  }
}

async function call(path, options = {}) {
  let res
  try {
    res = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    })
  } catch {
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
    throw new Error('Too many failed PIN attempts. Wait 60 seconds and try again.')
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

// Settings (apps.json): same idea as the database, its own PIN-bought token
const settingsHeaders = (token) => ({ 'X-Settings-Token': token })

export const openSettings = (pin) => call('/settings/open', { method: 'POST', body: JSON.stringify({ pin }) })

export const closeSettings = (token) => call('/settings/close', { method: 'POST', headers: settingsHeaders(token) })

export const getAppsConfig = (token) => call('/settings/apps', { headers: settingsHeaders(token) })

export const saveAppsConfig = (token, body) =>
  call('/settings/apps', { method: 'POST', headers: settingsHeaders(token), body: JSON.stringify(body) })

export const checkAppsEntry = (token, kind, spec) =>
  call('/settings/apps/check', { method: 'POST', headers: settingsHeaders(token), body: JSON.stringify({ kind, spec }) })
