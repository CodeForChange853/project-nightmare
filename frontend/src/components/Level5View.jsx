import { useCallback, useEffect, useRef, useState } from 'react'
import { getLiveWeather } from '../api'
import Icon from './Icon'
import WorkspaceStage from './WorkspaceStage'
import DashboardComposer from './DashboardComposer'
import FloatingResponse from './FloatingResponse'
import Orb from './Orb'
import ConversationWindow from './ConversationWindow'

const FALLBACK_ALLOWLIST_APPS = [
  { id: 'app-ppt', app_id: 'powerpoint', label: 'PowerPoint', command: 'open powerpoint', subtitle: 'Allowlisted · Click to open' },
  { id: 'app-word', app_id: 'word', label: 'Microsoft Word', command: 'open word', subtitle: 'Allowlisted · Click to open' },
  { id: 'app-excel', app_id: 'excel', label: 'Microsoft Excel', command: 'open excel', subtitle: 'Allowlisted · Click to open' },
  { id: 'app-term', app_id: 'terminal', label: 'Windows Terminal', command: 'open terminal', subtitle: 'Allowlisted · Click to open' },
]

function AppBadge({ appId = '', label = '' }) {
  const key = `${appId} ${label}`.toLowerCase()
  if (key.includes('powerpoint') || key.includes('ppt')) {
    return (
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-orange-500 to-red-600 text-[11px] font-black text-white shadow-[0_0_10px_rgba(249,115,22,0.45)]">
        P
      </div>
    )
  }
  if (key.includes('word')) {
    return (
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-700 text-[11px] font-black text-white shadow-[0_0_10px_rgba(59,130,246,0.45)]">
        W
      </div>
    )
  }
  if (key.includes('excel')) {
    return (
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-emerald-500 to-green-700 text-[11px] font-black text-white shadow-[0_0_10px_rgba(16,185,129,0.45)]">
        X
      </div>
    )
  }
  if (key.includes('terminal') || key.includes('wt') || key.includes('powershell')) {
    return (
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-[#ff2a4b]/50 bg-[#1a0409] font-mono text-[10px] font-bold text-[#ffd166] shadow-[0_0_10px_rgba(255,42,75,0.3)]">
        &gt;_
      </div>
    )
  }
  if (key.includes('vscode') || key.includes('code') || key.includes('antigravity')) {
    return (
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-sky-500 to-blue-700 font-mono text-[10px] font-bold text-white shadow-[0_0_10px_rgba(14,165,233,0.4)]">
        &lt;/&gt;
      </div>
    )
  }
  if (key.includes('chrome')) {
    return (
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-amber-500 to-red-600 text-[11px] font-bold text-white shadow-[0_0_10px_rgba(245,158,11,0.4)]">
        C
      </div>
    )
  }
  return (
    <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-[#ff2a4b]/40 bg-[#ff2a4b]/20 text-[11px] font-bold uppercase text-white">
      {(label || appId || 'A').slice(0, 1)}
    </div>
  )
}

export function Level5EyeLogo({ mode = 'idle', size = 38 }) {
  const isListening = mode === 'listening'
  return (
    <div
      style={{ width: size, height: size }}
      className={`relative shrink-0 rounded-full transition-shadow duration-500 ${
        isListening
          ? 'shadow-[0_0_32px_rgba(255,42,75,0.95),0_0_52px_rgba(255,209,102,0.65)]'
          : 'shadow-[0_0_22px_rgba(255,42,75,0.65),0_0_36px_rgba(255,209,102,0.28)]'
      }`}
      aria-hidden
    >
      <span className="absolute inset-[6%] rounded-full border border-[#ffd166]/70 bg-[radial-gradient(circle,rgba(65,12,20,0.95)_0%,rgba(19,7,10,0.8)_65%,transparent_100%)]" />
      <svg
        viewBox="0 0 100 100"
        className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
      >
        <ellipse
          cx="50"
          cy="50"
          rx="49"
          ry="18"
          transform="rotate(-20 50 50)"
          fill="none"
          stroke="#ffd166"
          strokeOpacity={isListening ? '0.95' : '0.65'}
          strokeWidth="1.4"
        />
        <circle
          cx="50"
          cy="50"
          r="44"
          fill="none"
          stroke="#ffd166"
          strokeOpacity="0.7"
          strokeWidth="1.5"
          strokeDasharray="10 5 3 5"
          className="origin-center orbit-slow"
        />
      </svg>
      <Orb mode={mode} clearanceLevel={5} track={false} className="relative" />
    </div>
  )
}

export default function Level5View({
  status,
  categories = [],
  activeKey = 'projects',
  onCategory,
  selectedId = null,
  selectedItem = null,
  onSelect,
  onActivate,
  mode = 'idle',
  title = 'Watching',
  caption = 'Hold the eye or Space to talk',
  caption2 = null,
  focus = null,
  asleep = false,
  bootDone = true,
  entries = [],
  busy = false,
  disabled = false,
  workingTarget = null,
  elapsed = 0,
  listening = false,
  interim = '',
  speaking = false,
  speechProgress = null,
  canTalk = true,
  speechError = '',
  onPressStart,
  onPressEnd,
  onSubmit,
  onSpeak,
  onStopSpeaking,
  onOpenSettings,
  onOpenDb,
  onOpenHelp,
  onOpenDefense,
  onOpenTeamTimeline,
  onOpenEmails,
  onOpenTelemetry,
  onMinimizeWindow,
  onToggleMaximize,
}) {
  const [activeNav, setActiveNav] = useState('home')
  const [showLogDrawer, setShowLogDrawer] = useState(false)
  const [todayOpen, setTodayOpen] = useState(false)
  const [browseOverride, setBrowseOverride] = useState(null)
  const toolsMenu = useRef(null)
  const todayToggle = useRef(null)
  const historyToggle = useRef(null)
  const closeHistory = () => { setShowLogDrawer(false); requestAnimationFrame(() => historyToggle.current?.focus()) }
  const readonly = status?.role === 'readonly'
  const commandDisabled = disabled || busy || mode === 'offline'
  const stateLabel = mode === 'offline' ? 'Offline' : listening ? 'Listening' : busy ? 'Working' : speaking ? 'Speaking' : asleep ? 'Standby' : 'Ready'
  const currentAnswer = entries.findLast((entry) => entry.role !== 'you')
  const lastQuestion = entries.findLast((entry) => entry.role === 'you')
  const turnId = lastQuestion?.id ?? null
  const responseNode = ['projects', 'apps', 'reminders', 'tasks'].includes(currentAnswer?.focus?.node) ? currentAnswer.focus.node : null
  const browseKey = browseOverride?.turnId === turnId ? browseOverride.key : responseNode
  const browse = (key) => { setBrowseOverride({ key, turnId }); onSelect?.(null) }

  useEffect(() => {
    const close = (event) => {
      if (event.type === 'pointerdown' && !toolsMenu.current?.contains(event.target)) toolsMenu.current?.removeAttribute('open')
      if (event.key === 'Escape') {
        if (toolsMenu.current?.contains(document.activeElement)) toolsMenu.current.querySelector('summary')?.focus()
        toolsMenu.current?.removeAttribute('open')
        if (document.getElementById('dashboard-today')?.contains(document.activeElement)) todayToggle.current?.focus()
        setTodayOpen(false)
      }
    }
    window.addEventListener('pointerdown', close)
    window.addEventListener('keydown', close)
    return () => { window.removeEventListener('pointerdown', close); window.removeEventListener('keydown', close) }
  }, [])
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem('nightmare_l5_sidebar_collapsed') === '1'
    } catch {
      return false
    }
  })

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem('nightmare_l5_sidebar_collapsed', next ? '1' : '0')
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  // Keep the header clock fresh without rerendering every second.
  const [nowTime, setNowTime] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNowTime(new Date()), 15_000)
    return () => clearInterval(id)
  }, [])

  // Visual standby only; operator clearance remains permanently Level 5.
  const [idleStandby, setIdleStandby] = useState(false)
  const lastActivityRef = useRef(Date.now())

  useEffect(() => {
    const markActive = () => {
      lastActivityRef.current = Date.now()
      setIdleStandby((prev) => (prev ? false : prev))
    }
    const events = ['pointerdown', 'keydown', 'wheel']
    events.forEach((ev) => window.addEventListener(ev, markActive, { passive: true }))
    return () => events.forEach((ev) => window.removeEventListener(ev, markActive))
  }, [])

  useEffect(() => {
    if (listening || busy || speaking) {
      lastActivityRef.current = Date.now()
      setIdleStandby(false)
    }
  }, [listening, busy, speaking])

  useEffect(() => {
    const id = setInterval(() => {
      if (listening || busy || speaking) return
      if (Date.now() - lastActivityRef.current > 90_000) {
        setIdleStandby(true)
      }
    }, 5_000)
    return () => clearInterval(id)
  }, [listening, busy, speaking])

  const isDeepIdle = asleep || idleStandby
  // Real Live Weather State (strictly zero placeholder numbers, updates hourly)
  const [liveWeather, setLiveWeather] = useState(() => status?.weather_card || null)
  const [weatherLoading, setWeatherLoading] = useState(false)
  const [weatherError, setWeatherError] = useState(null)
  const [lastWeatherCallAt, setLastWeatherCallAt] = useState(() =>
    status?.weather_card?.updated_at || null
  )
  const initialWeatherFetchedRef = useRef(false)

  useEffect(() => {
    if (status?.weather_card) {
      setLiveWeather(status.weather_card)
      setWeatherError(null)
      if (status.weather_card.updated_at) {
        setLastWeatherCallAt(status.weather_card.updated_at)
      } else {
        setLastWeatherCallAt((prev) =>
          prev || new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
        )
      }
    }
  }, [status?.weather_card])

  const refreshLiveWeather = useCallback(async (force = false) => {
    setWeatherLoading(true)
    setWeatherError(null)
    const callTimeStr = new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    try {
      const res = await getLiveWeather('', force)
      if (res?.weather) {
        setLiveWeather(res.weather)
        setLastWeatherCallAt(res.weather.updated_at || callTimeStr)
      }
    } catch (err) {
      setWeatherError('Weather is unavailable. Try refreshing in a moment.')
    } finally {
      setWeatherLoading(false)
    }
  }, [])

  // Fetch once on mount if not already cached, then auto-update only once per hour (3,600,000 ms)
  useEffect(() => {
    if (!initialWeatherFetchedRef.current) {
      initialWeatherFetchedRef.current = true
      if (!status?.weather_card) {
        refreshLiveWeather(false)
      }
    }
    const hourlyTimer = setInterval(() => {
      refreshLiveWeather(false)
    }, 3_600_000)
    return () => clearInterval(hourlyTimer)
  }, [refreshLiveWeather, status?.weather_card])

  // Minimized Recent Activity: only allowlisted applications so they can be re-opened
  const recentApps =
    status?.recent_apps && status.recent_apps.length > 0
      ? status.recent_apps.slice(0, 4)
      : (status?.apps ?? []).slice(0, 4).map((appId) => FALLBACK_ALLOWLIST_APPS.find((app) => app.app_id === appId)
        ?? { app_id: appId, label: appId, command: `open ${appId}`, subtitle: 'Allowlisted · Click to open' })

  const liveNotes = status?.notes ?? []
  const reminders = liveNotes.slice(0, 3).map((n) => ({
    id: n.id,
    text: n.text,
    time: n.ts ? `Added ${new Date(n.ts).toLocaleDateString([], { month: 'short', day: 'numeric' })}` : 'Active',
  }))

  const liveTasks = status?.measurable_tasks ?? []
  const priorities = liveTasks.slice(0, 3).map((t) => {
    const pct =
      t.target_progress > 0
        ? Math.min(100, Math.round((t.current_progress / t.target_progress) * 100))
        : Math.min(100, Number(t.current_progress) || 0)
    return {
      id: t.id,
      title: t.title,
      priority: ['high', 'medium', 'low'].includes(String(t.priority).toLowerCase()) ? String(t.priority).toLowerCase() : null,
      pct,
    }
  })

  const liveEvents = status?.calendar_events ?? []
  const dayStart = new Date(nowTime).setHours(0, 0, 0, 0)
  const timelineItems = liveEvents.filter((ev) => ev.start_date && new Date(ev.start_date).getTime() >= (/^\d{4}-\d{2}-\d{2}$/.test(ev.start_date) ? dayStart : nowTime.getTime()))
    .sort((a, b) => new Date(a.start_date) - new Date(b.start_date)).slice(0, 3).map((ev) => {
    const d = ev.start_date ? new Date(ev.start_date) : null
    const valid = d && !Number.isNaN(d.getTime())
    const dateBadge = valid
      ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      : String(ev.start_date || 'Scheduled').slice(0, 6)
    const timeStr = /^\d{4}-\d{2}-\d{2}$/.test(ev.start_date) ? 'All day' : valid
      ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : ev.event_type || 'All Day'
    return {
      id: ev.id,
      date: dateBadge,
      title: ev.title,
      time: timeStr,
    }
  })

  const navItems = [
    { key: 'home', label: 'Home', icon: 'eye' },
    { key: 'projects', label: 'Projects', icon: 'folder' },
    { key: 'reminders', label: 'Reminders', icon: 'bell' },
    { key: 'weather', label: 'Weather', icon: 'globe' },
    { key: 'docs', label: 'Documentation', icon: 'doc' },
    { key: 'apps', label: 'Allowlisted Apps', icon: 'app' },
    { key: 'timeline', label: 'Team Timeline', icon: 'bell' },
    { key: 'settings', label: 'Settings', icon: 'sliders' },
  ]

  const handleNavClick = (key) => {
    if (['home', 'projects', 'reminders', 'apps'].includes(key)) setShowLogDrawer(false)
    if (key === 'timeline') {
      onOpenTeamTimeline?.()
      return
    }
    if (key === 'settings') {
      onOpenSettings?.()
      return
    }
    if (key === 'weather') {
      setActiveNav('home')
      refreshLiveWeather(true)
      onSubmit('what is the weather')
      return
    }
    if (key === 'reminders') {
      browse('reminders')
      setActiveNav('reminders')
      onCategory?.('reminders')
      return
    }
    if (key === 'projects') {
      browse('projects')
      setActiveNav('projects')
      onCategory?.('projects')
      return
    }
    if (key === 'apps') {
      browse('apps')
      setActiveNav('apps')
      onCategory?.('apps')
      return
    }
    if (key === 'docs') {
      setActiveNav('home')
      onSubmit('what is project-nightmare about')
      return
    }
    if (key === 'home') browse(null)
    setActiveNav(key)
  }

  const tools = [
    { label: 'Command reference', icon: 'bolt', run: onOpenHelp },
    { label: 'Defense co-pilot', icon: 'presentation', run: onOpenDefense, full: true },
    { label: 'Hardware telemetry', icon: 'cpu', run: onOpenTelemetry },
    { label: 'Priority inbox', icon: 'mail', run: onOpenEmails },
    { label: 'Router review', icon: 'branch', run: () => onSubmit('/review') },
    { label: 'Database & audit', icon: 'database', run: onOpenDb },
    { label: 'Settings & allowlist', icon: 'sliders', run: onOpenSettings, full: true },
    { label: isDeepIdle ? 'Wake eye' : 'Eye standby', icon: 'eye', run: () => setIdleStandby((v) => !v) },
  ]

  return (
    <div className="dashboard-shell">
      <div className="l5-frame dashboard-frame">
        <header className="dashboard-header">
          <div className="dashboard-brand">
            <button type="button" className="dashboard-icon-button sidebar-toggle" onClick={toggleSidebar} aria-label="Toggle navigation sidebar" aria-expanded={!sidebarCollapsed}><Icon name="log" size={19} /></button>
            <Level5EyeLogo mode={mode} size={36} />
            <div><div className="dashboard-wordmark"><span>PROJECT</span> NIGHTMARE</div><p>Local · Secure · Your assistant</p></div>
          </div>
          <div className="dashboard-header-actions">
            <span className={`dashboard-connection ${mode === 'offline' ? 'is-offline' : ''}`}><span />{mode === 'offline' ? 'Offline' : readonly ? 'Viewing only' : 'Local assistant'}</span>
            <button type="button" className="dashboard-clearance" onClick={() => onSubmit('clearance status')} title={readonly ? 'Remote access cannot run actions or change settings' : 'Permanent Level 5 Architect clearance'}>{readonly ? 'Read-only' : <>L5 <span>Architect</span></>}</button>
            <button ref={historyToggle} type="button" className="dashboard-header-button" onClick={() => setShowLogDrawer(true)} aria-haspopup="dialog" aria-expanded={showLogDrawer}><Icon name="log" size={15} />History</button>
            <button ref={todayToggle} type="button" className="dashboard-header-button today-toggle" aria-controls="dashboard-today" aria-expanded={todayOpen} onClick={() => setTodayOpen((v) => !v)}>Today</button>
            <details className="dashboard-tools" ref={toolsMenu}>
              <summary className="dashboard-header-button"><Icon name="app" size={15} />Tools</summary>
              <div className="dashboard-tools-menu">{tools.filter((tool) => !(readonly && tool.full)).map((tool) => <button key={tool.label} type="button" onClick={() => { toolsMenu.current?.removeAttribute('open'); tool.run?.() }}><Icon name={tool.icon} size={16} />{tool.label}</button>)}</div>
            </details>
            <div className="dashboard-clock"><strong>{nowTime.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</strong><span>{nowTime.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span></div>
            <div className="dashboard-window-controls">
              <button type="button" onClick={onMinimizeWindow} aria-label="Minimize window">−</button>
              <button type="button" onClick={onToggleMaximize} aria-label="Maximize window">□</button>
              <button type="button" onClick={() => onSubmit('go to sleep')} aria-label="Put to sleep"><Icon name="close" size={15} /></button>
            </div>
          </div>
        </header>
        <div className={`dashboard-grid ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
          <aside className="dashboard-sidebar">
            <nav aria-label="Main navigation">{navItems.filter((item) => !(readonly && ['apps', 'settings'].includes(item.key))).map((item) => <button
              key={item.key} type="button" title={item.label} aria-label={item.label}
              aria-current={activeNav === item.key ? 'page' : undefined}
              onClick={() => handleNavClick(item.key)}>
              <Icon name={item.icon} size={18} /><span>{item.label}</span>
            </button>)}</nav>
            <button type="button" className="dashboard-security" onClick={() => onSubmit('clearance status')} title={readonly ? 'Read-only access' : 'Local processing · Allowlist active · Level 5 Architect'}><Icon name="shield" size={18} /><span><strong>{readonly ? 'Read-only access' : 'Local & secure'}</strong><small>{readonly ? 'Viewing only' : 'Allowlist active · Level 5'}</small></span></button>
          </aside>
          <main className="dashboard-main">
            <div className="dashboard-landscape" aria-hidden />
            <div className="dashboard-section-heading"><div><span className="dashboard-eyebrow">COMMAND CENTER</span><h2>Your workspace</h2></div><span className={`dashboard-state ${listening || busy ? 'is-active' : ''}`}><span />{stateLabel}{busy ? ` · ${elapsed}s` : ''}</span></div>
              <WorkspaceStage categories={categories} browseKey={browseKey} onDismiss={() => { browse(null); setActiveNav('home') }}
                selectedId={selectedId} selectedItem={selectedItem} onSelect={onSelect} onActivate={onActivate}
                mode={mode} title={stateLabel} caption={caption} caption2={caption2} busy={busy} bootDone={bootDone}
                canTalk={canTalk} onPressStart={onPressStart} onPressEnd={onPressEnd} focus={focus} asleep={isDeepIdle}
                onSubmit={onSubmit} readonly={readonly} disabled={commandDisabled}
                response={!busy && currentAnswer ? <FloatingResponse answer={currentAnswer} speechProgress={speechProgress} /> : null} />
            {showLogDrawer && <ConversationWindow entries={entries} busy={busy} elapsed={elapsed} onSpeak={onSpeak} onClose={closeHistory} />}
            {!readonly && <div className="dashboard-recent" aria-label="Recent apps"><span>{status?.recent_apps?.length ? 'Recent apps' : 'Quick launch'}</span><div className="no-scrollbar">{recentApps.map((app) => <button key={app.id || app.app_id} type="button" disabled={commandDisabled} onClick={() => onSubmit(app.command || `open ${app.app_id}`)} title={`${app.label} · ${app.subtitle}`}><AppBadge appId={app.app_id} label={app.label} /><span>{app.label}</span></button>)}</div></div>}
            <DashboardComposer disabled={commandDisabled} listening={listening} interim={interim} canTalk={canTalk}
              onPressStart={onPressStart} onPressEnd={onPressEnd} onSubmit={onSubmit} speaking={speaking} onStopSpeaking={onStopSpeaking} readonly={readonly} speechError={speechError} />
          </main>
          <aside id="dashboard-today" aria-label="Today" className={`dashboard-today scroll-thin ${todayOpen ? 'is-open' : ''}`}>
            <div className="dashboard-today-heading"><div><span className="dashboard-eyebrow">AT A GLANCE</span><h2>Today</h2></div><button type="button" className="today-close dashboard-icon-button" aria-label="Close Today" onClick={() => { setTodayOpen(false); todayToggle.current?.focus() }}><Icon name="close" size={18} /></button></div>
            {/* 2. Today's Reminders Card */}
            <div className="l5-card rounded-xl p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[12px] font-bold text-white">
                  <span className="text-[#ff2a4b]">
                    <Icon name="bell" size={14} />
                  </span>
                  <span>Reminders &amp; notes</span>
                </div>
                <button
                  type="button"
                  onClick={() => onSubmit('what are my reminders')}
                  className="text-[10.5px] font-medium text-[#ff5466] hover:text-white transition"
                >
                  View All →
                </button>
              </div>

              {reminders.length > 0 ? (
                <div className="divide-y divide-[#ff2a4b]/15">
                  {reminders.map((rem) => (
                    <div key={rem.id} className="flex items-start gap-2 py-1.5 first:pt-0 last:pb-0">
                      <button
                        type="button"
                        onClick={() => onSubmit(`complete reminder ${rem.id}`)}
                        title={`Complete reminder #${rem.id}`}
                        disabled={readonly || commandDisabled}
                        aria-label={`Complete reminder: ${rem.text}`}
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded-full border border-[#ff2a4b]/70 hover:bg-[#ff2a4b]/30 transition"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[11.5px] font-semibold text-white">{rem.text}</div>
                        <div className="text-[10px] text-ash">{rem.time}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-2 text-[11px] text-ash">
                  No open reminders. Say &ldquo;remind me to...&rdquo; to add one.
                </p>
              )}
            </div>

            {/* 3. Workspace Priorities Card */}
            <div className="l5-card rounded-xl p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[12px] font-bold text-white">
                  <span className="text-[#ff2a4b]">
                    <Icon name="gauge" size={14} />
                  </span>
                  <span>Workspace Priorities</span>
                </div>
                <button
                  type="button"
                  onClick={onOpenTeamTimeline}
                  className="text-[10.5px] font-medium text-[#ff5466] hover:text-white transition"
                >
                  View All →
                </button>
              </div>

              {priorities.length > 0 ? (
                <div className="space-y-2">
                  {priorities.map((item) => (
                    <div key={item.id}>
                      <div className="flex items-center justify-between gap-2 text-[11px]">
                        <span className="truncate font-medium text-white">{item.title}</span>
                        {item.priority && <span
                          className={`rounded px-1.5 py-0.2 text-[9.5px] font-bold ${
                            item.priority === 'high'
                              ? 'bg-[#ff2a4b]/25 text-[#ff5466] border border-[#ff2a4b]/40'
                              : 'bg-amber-500/20 text-amber-300 border border-amber-500/35'
                          }`}
                        >
                          {item.priority}
                        </span>}
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-[#dc143c] to-[#ff5466] shadow-[0_0_8px_#ff2a4b]"
                            style={{ width: `${item.pct}%` }}
                          />
                        </div>
                        <span className="w-7 text-right font-mono text-[10px] text-ash">{item.pct}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="py-2 text-sm text-ash">No tracked tasks yet. Ask Nightmare to track a goal.</p>
              )}
            </div>

            {/* 4. Team Timeline Card */}
            <div className="l5-card rounded-xl p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[12px] font-bold text-white">
                  <span className="text-[#ff2a4b]">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="4" width="18" height="17" rx="2" />
                      <path d="M16 2v4M8 2v4M3 10h18" />
                    </svg>
                  </span>
                  <span>Upcoming events</span>
                </div>
                <button
                  type="button"
                  onClick={onOpenTeamTimeline}
                  className="text-[10.5px] font-medium text-[#ff5466] hover:text-white transition"
                >
                  View All →
                </button>
              </div>

              {timelineItems.length > 0 ? (
                <div className="space-y-1.5">
                  {timelineItems.map((ev) => (
                    <div
                      key={ev.id}
                      onClick={onOpenTeamTimeline}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpenTeamTimeline?.() } }}
                      className="flex cursor-pointer items-center justify-between gap-2 rounded-lg py-0.5 text-[11px] hover:bg-white/5 px-1 transition"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-sm bg-[#ff2a4b]" />
                        <span className="w-11 shrink-0 font-semibold text-ash">{ev.date}</span>
                        <span className="truncate font-medium text-white">{ev.title}</span>
                      </div>
                      <span className="shrink-0 font-mono text-[10px] text-ash">{ev.time}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={onOpenTeamTimeline}
                  className="w-full rounded-lg border border-[#ff2a4b]/30 bg-[#190409]/70 px-3 py-2 text-left text-[11px] text-bone hover:border-[#ff2a4b] transition"
                >
                  <div className="font-semibold text-white">No upcoming events</div>
                  <div className="text-[10px] text-ash">Open the team timeline →</div>
                </button>
              )}
            </div>

            {/* 1. Real Live Weather Card (Zero Placeholders, Hourly Sync) */}
            <div className="l5-card rounded-xl p-3">
              <div className="mb-2 text-sm font-semibold text-white">Weather</div>
              {weatherError && liveWeather && <p className="mb-2 text-xs text-bile" role="status">Refresh unavailable. Showing the last update.</p>}
              {liveWeather ? (
                <div>
                  <div className="grid grid-cols-[1fr_auto] items-center gap-2.5">
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="relative flex h-8 w-10 shrink-0 items-center justify-center">
                          <span className="absolute right-0.5 top-0 h-4 w-4 rounded-full bg-amber-400 shadow-[0_0_10px_#fbbf24]" />
                          <svg viewBox="0 0 32 24" className="relative z-10 h-6 w-8 fill-slate-100 drop-shadow">
                            <path d="M24.5 21H9a5.5 5.5 0 0 1-.6-10.97A7.5 7.5 0 0 1 23 11.5a4.5 4.5 0 0 1 1.5 9.5z" />
                          </svg>
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-[12.5px] font-bold text-white">{liveWeather.city}</div>
                          <div className="truncate text-[10.5px] text-ash">{liveWeather.condition}</div>
                        </div>
                      </div>
                      <div className="mt-1.5 flex items-baseline gap-2.5">
                        <span className="text-[26px] font-bold leading-none text-white">
                          {String(liveWeather.temp_c).replace(/°C$/i, '')}°C
                        </span>
                        <span className="text-[10.5px] text-ash">
                          H: {String(liveWeather.high_c ?? liveWeather.temp_c).replace(/[°C]+$/i, '')}° L:{' '}
                          {String(liveWeather.low_c ?? liveWeather.temp_c).replace(/[°C]+$/i, '')}°
                        </span>
                      </div>
                    </div>

                    <div className="space-y-1 border-l border-[#ff2a4b]/20 pl-3 text-[10.5px]">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-ash">Humidity</span>
                        <span className="font-semibold text-white">{liveWeather.humidity}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-ash">Wind</span>
                        <span className="font-semibold text-white">{liveWeather.wind}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-ash">UV Index</span>
                        <span className="font-semibold text-white">{liveWeather.uv_index}</span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-1.5 flex items-center justify-between border-t border-[#ff2a4b]/15 pt-1 text-[9.5px] font-mono text-ash">
                    <span>
                      Updated: <strong className="text-white/90">{lastWeatherCallAt || liveWeather.updated_at || 'Just now'}</strong> · Hourly (1h)
                    </span>
                    <button
                      type="button"
                      disabled={weatherLoading}
                      onClick={() => refreshLiveWeather(true)}
                      className="rounded px-1.5 py-0.5 text-[9.5px] text-[#ff5466] transition hover:bg-[#ff2a4b]/15 hover:text-white disabled:opacity-50"
                      title="Force refresh live weather now"
                    >
                      {weatherLoading ? 'Syncing…' : '↻ Refresh'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between py-2 text-xs text-ash">
                  <div className="min-w-0">
                    <div className="truncate">
                      {weatherLoading ? 'Fetching live weather...' : weatherError || 'Live weather ready'}
                    </div>
                    {lastWeatherCallAt && (
                      <div className="mt-0.5 font-mono text-[9.5px] text-ash/80">
                        Updated: {lastWeatherCallAt} · Updates hourly (1h)
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    disabled={weatherLoading}
                    onClick={() => refreshLiveWeather(true)}
                    className="shrink-0 rounded border border-[#ff2a4b]/30 bg-[#ff2a4b]/15 px-2 py-1 font-mono text-[10px] text-[#ff5466] transition hover:bg-[#ff2a4b]/30 hover:text-white disabled:opacity-50"
                  >
                    {weatherLoading ? '…' : '↻ Fetch'}
                  </button>
                </div>
              )}
            </div>


            <button type="button" className="dashboard-help" onClick={onOpenHelp}><Icon name="bolt" size={16} /><span>Explore commands</span><Icon name="chevron" size={14} /></button>
          </aside>
        </div>
      </div>
    </div>
  )
}
