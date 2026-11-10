import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AuthError, confirmAction, getRouterReview, approveRouterMiss, getStatus, loginPin, logoutSession, resetSession, sendChat, setWindowMode } from './api'
import Background from './components/Background'
import Boot from './components/Boot'
import ConfirmDialog from './components/ConfirmDialog'
import DatabasePanel from './components/DatabasePanel'
import DefensePanel from './components/DefensePanel'
import HelpPanel from './components/HelpPanel'
import Icon from './components/Icon'
import Level5View from './components/Level5View'
import LockScreen from './components/LockScreen'
import MiniView from './components/MiniView'
import PhoneView from './components/PhoneView'
import SettingsPanel from './components/SettingsPanel'
import SpeechPanel from './components/SpeechPanel'
import StatusBar from './components/StatusBar'
import TeamProgressPanel, { getEmailDomainMeta } from './components/TeamProgressPanel'
import { useRecognizer, useSpeaker } from './utils/useSpeech'

let nextId = 1
const isTyping = (el) => el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)
// inside a dialog Space belongs to its checkboxes and buttons, not push-to-talk
const ownsSpace = (el) => isTyping(el) || Boolean(el?.closest?.('[role="dialog"]'))
// phones have no Space bar to hold, so the hints talk about the eye instead
const TOUCH = window.matchMedia('(pointer: coarse)').matches
const HOLD = TOUCH ? 'Hold the eye' : 'Hold Space'
// below lg the panel sits under the graph, so on a phone it has to be scrolled to
const stacked = () => window.matchMedia('(max-width: 1023px)').matches

// The Ctrl+Alt+N helper opens /?mini in a small always-on-top window. That window shows the mini view
// while it is narrow; the page asks the helper for another size through its title, which the helper
// watches: "Nightmare Mini" = small and on top, "Nightmare" = maximized.
const MINI_HOST = new URLSearchParams(window.location.search).has('mini')
const MINI_TITLE = 'Nightmare Mini'
const FULL_TITLE = 'Nightmare'

function useMedia(query) {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}

const VOICE_CMD_RE =
  /^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:(?:switch|change|set|use)\s+(?:the\s+)?(?:voice\s+to|to\s+)?(?<g1>male|female)(?:\s+voice)?|(?<g2>male|female)\s+voice)\s*[.?!]*$/i
const SPEED_FASTER_RE =
  /^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:speak|read|talk)\s+(?:faster|quicker|speed\s+up)\s*[.?!]*$/i
const SPEED_SLOWER_RE =
  /^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:speak|read|talk)\s+(?:slower|slow\s+down)\s*[.?!]*$/i
const SPEED_NORMAL_RE =
  /^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:normal|default|reset)\s+(?:speaking\s+|reading\s+|voice\s+)?speed\s*[.?!]*$/i

const QUICK_ASKS = [
  { title: 'Which project needs attention?', command: 'which project needs attention?' },
  { title: 'Whatâ€™s the weather?', command: 'what is the weather' },
  { title: 'List my projects', command: 'list my projects' },
  { title: 'What are my reminders?', command: 'what are my reminders' },
  { title: 'How many calls today?', command: 'how many calls today' },
  { title: 'Open the database', command: 'database access open', full: true },
]

// node key -> item id prefix used in buildCategories, so a reply's focus can point at an item
const FOCUS_PREFIX = { projects: 'project', reminders: 'note', apps: 'app', tasks: 'task', asks: 'ask' }

const SLEEP_AFTER_MS = 5 * 60 * 1000 // idle this long and Nightmare dozes off
const WAKE_RE =
  /^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:wake\s+up|are\s+you\s+(?:awake|there)\s+nightmare|rise\s+and\s+shine)(?:[, ]+nightmare)?\s*[.?!]*$/i
const SLEEP_RE =
  /^\s*(?:(?:hey|ok)\s+)?(?:nightmare[, ]+)?(?:go\s+to\s+sleep|(?:mayor|major|may\s+or|to|go|2)\s+sleep|sleep(?:\s+now)?|take\s+a\s+nap|good\s*night)(?:[, ]+nightmare)?\s*[.?!]*$/i
const GREETING = 'Hello, Nightmare is awake. What are we going to do today?'
const HOME_RE =
  /^\s*(?:(?:hey|ok)\s+)?(?:nightmare[, ]+)?(?:(?:go\s+)?home|(?:go\s+)?full\s*screen|full\s+view|show\s+(?:me\s+)?everything|open\s+(?:the\s+)?full\s+(?:view|nightmare|screen))(?:[, ]+nightmare)?\s*[.?!]*$/i
const MINI_RE =
  /^\s*(?:(?:hey|ok)\s+)?(?:nightmare[, ]+)?(?:(?:go\s+|oo\s+|ou\s+|u\s+|you\s+|to\s+)?mini|(?:go\s+)?small|small\s+window|mini\s+(?:mode|window|view)|minimi[sz]e(?:\s+nightmare)?)(?:[, ]+nightmare)?\s*[.?!]*$/i
const HELPER_CMD_RE =
  /^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?(?:please\s+)?(?:open|show|display|launch|view)\s+(?:the\s+)?(?:developer\s+)?helper(?:\s+function|\s+ui|\s+panel|\s+window)?\s*[.?!]*$|^\s*(?:(?:hey|ok|hi)\s+)?(?:nightmare[, ]+)?developer\s+helper(?:\s+function|\s+ui|\s+panel|\s+window)?\s*[.?!]*$/i

/**
 * Open a website the backend chose (fixed https templates only) as a tab in this browser.
 * Returns false when the popup blocker stops it, so the reply can offer a link instead.
 */
function openInBrowser(url) {
  if (!/^https:\/\//i.test(url)) return false
  const tab = window.open(url, '_blank')
  if (!tab) return false
  tab.opener = null
  return true
}

const DAY_MS = 86_400_000
const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

function relTime(iso) {
  if (!iso) return 'Unknown'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const diff = Date.now() - d.getTime()
  if (diff < 3_600_000) return rtf.format(-Math.max(1, Math.round(diff / 60_000)), 'minute')
  if (diff < DAY_MS) return rtf.format(-Math.round(diff / 3_600_000), 'hour')
  if (diff < 7 * DAY_MS) return rtf.format(-Math.round(diff / DAY_MS), 'day')
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function freshnessMeter(card) {
  if (!card.has_handoff || !card.updated_at) return 0
  const diff = Date.now() - new Date(card.updated_at).getTime()
  if (diff < DAY_MS) return 3
  if (diff < 7 * DAY_MS) return 2
  return 1
}

function buildCategories(status) {
  const cards = status?.project_cards ?? []
  const notes = status?.notes ?? []
  const apps = status?.apps ?? []
  const tasks = status?.tasks ?? []
  const hasVscode = apps.includes('vscode')
  // the phone can't open or run anything, so it gets no Apps or Tasks nodes at all
  const readonly = status?.role === 'readonly'

  return [
    {
      key: 'projects',
      label: 'Projects',
      icon: 'folder',
      empty: 'No project folders found on your Desktop.',
      items: cards.map((c) => {
        const dirty = c.git?.dirty ?? 0
        return {
          id: `project:${c.name}`,
          kind: 'project',
          icon: 'folder',
          kindLabel: 'Project',
          title: c.name,
          tag: c.git ? `${c.git.branch}${dirty ? ` +${dirty}` : ''}` : c.has_handoff ? 'handoff' : 'no handoff',
          tone: dirty ? 'warn' : 'muted',
          meter: freshnessMeter(c),
          badge: c.has_handoff ? { text: 'Handoff found' } : { text: 'No handoff', tone: 'warn' },
          facts: [
            { label: 'Handoff updated', value: c.has_handoff ? relTime(c.updated_at) : 'No handoff.md' },
            { label: 'Branch', value: c.git?.branch ?? 'Not a git repo' },
            ...(c.git ? [{ label: 'Uncommitted files', value: String(dirty) }] : []),
          ],
          body:
            c.cached_summary ||
            (c.has_handoff
              ? 'No summary yet. Read progress and Nightmare will summarize handoff.md.'
              : c.has_readme
                ? 'This folder has no handoff.md, so there is no progress log. Ask what it is about to hear its README.'
                : 'This folder has no handoff.md or README yet, so there is nothing to summarize.'),
          actions: [
            ...(c.has_handoff ? [{ label: 'Read progress', command: `progress of ${c.name}` }] : []),
            ...(c.has_readme || c.has_handoff ? [{ label: 'What itâ€™s about', command: `what is ${c.name} about` }] : []),
            ...(c.git ? [{ label: 'Git status', command: `git status of ${c.name}` }] : []),
            { label: 'Open folder', command: `open the ${c.name} folder`, full: true },
            ...(hasVscode ? [{ label: 'Open in VS Code', command: `open ${c.name} in vs code`, full: true }] : []),
          ],
        }
      }),
    },
    {
      key: 'reminders',
      label: 'Reminders',
      icon: 'bell',
      empty: 'No open reminders. Say â€œremind me to â€¦â€ to add one.',
      items: notes.map((n) => ({
        id: `note:${n.id}`,
        kind: 'note',
        icon: 'bell',
        kindLabel: `Reminder #${n.id}`,
        title: n.text,
        tag: `#${n.id}`,
        tone: 'hot',
        meter: null,
        facts: [{ label: 'Added', value: relTime(n.ts) }],
        actions: [{ label: 'Mark done', command: `complete reminder ${n.id}` }],
      })),
    },
    {
      key: 'apps',
      label: 'Apps',
      icon: 'app',
      empty: 'No apps in apps.json yet.',
      items: apps.map((a) => ({
        id: `app:${a}`,
        kind: 'app',
        icon: 'app',
        kindLabel: 'App',
        title: a,
        tag: 'allowlisted',
        meter: null,
        body: 'Listed in backend/apps.json. Nightmare can only open apps from that list.',
        actions: [{ label: `Open ${a}`, command: `open ${a}`, full: true }],
      })),
    },
    {
      key: 'tasks',
      label: 'Tasks',
      icon: 'bolt',
      empty: 'No tasks in apps.json yet.',
      items: tasks.map((t) => ({
        id: `task:${t}`,
        kind: 'task',
        icon: 'bolt',
        kindLabel: 'Task',
        title: t,
        tag: 'task',
        tone: 'hot',
        meter: null,
        body: 'Runs the command defined for this task in backend/apps.json. Youâ€™ll see the exact command before anything runs if the task needs confirmation.',
        actions: [{ label: 'Run task', command: `run ${t}`, full: true }],
      })),
    },
    {
      key: 'asks',
      label: 'Quick asks',
      icon: 'spark',
      empty: '',
      items: QUICK_ASKS.filter((q) => !(readonly && q.full)).map((q) => ({
        id: `ask:${q.command}`,
        kind: 'ask',
        icon: 'spark',
        kindLabel: 'Quick ask',
        title: q.title,
        tag: 'ask',
        meter: null,
        body: `Sends â€œ${q.command}â€ to Nightmare.`,
        actions: [{ label: 'Ask', command: q.command }],
      })),
    },
  ].filter((c) => !(readonly && (c.key === 'apps' || c.key === 'tasks')))
}

export default function App() {
  const [entries, setEntries] = useState([])
  const [status, setStatus] = useState(null)
  const [bootLoaded, setBootLoaded] = useState(false)
  const [bootDone, setBootDone] = useState(false)
  const [locked, setLocked] = useState(false)
  const [pinInput, setPinInput] = useState('')
  const [pinError, setPinError] = useState('')
  const [pending, setPending] = useState(null)
  const [busy, setBusy] = useState(false)
  const [workingTarget, setWorkingTarget] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [history, setHistory] = useState([])
  const [activeKey, setActiveKey] = useState('projects')
  const [selectedId, setSelectedId] = useState(null)
  const [panelTab, setPanelTab] = useState('details')
  const [unread, setUnread] = useState(0)
  const [dbOpen, setDbOpen] = useState(false)
  const closeDbPanel = useCallback(() => setDbOpen(false), [])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const closeSettingsPanel = useCallback(() => setSettingsOpen(false), [])
  const [helpOpen, setHelpOpen] = useState(false)
  const closeHelp = useCallback(() => setHelpOpen(false), [])
  const [teamProgressOpen, setTeamProgressOpen] = useState(false)
  const [teamProgressData, setTeamProgressData] = useState(null)
  const [teamProgressTab, setTeamProgressTab] = useState('summary')
  const closeTeamProgress = useCallback(() => setTeamProgressOpen(false), [])

  // Global Real-Time SSE Priority Email Feed
  const [emailToasts, setEmailToasts] = useState([])
  const [latestSseEmail, setLatestSseEmail] = useState(null)
  const prevEmailIdsRef = useRef(new Set())
  const dismissEmailToast = useCallback((id) => {
    setEmailToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])
  const [defenseOpen, setDefenseOpen] = useState(false)
  const [defenseData, setDefenseData] = useState(null)
  const closeDefense = useCallback(() => setDefenseOpen(false), [])

  const [asleep, setAsleep] = useState(false)
  // layouts: the helper's mini window, the phone (tab bar) and the desktop graph
  const narrowWindow = useMedia('(max-width: 599px)')
  const phoneWidth = useMedia('(max-width: 767px)')
  const [wantFull, setWantFull] = useState(false) // mini window asked to be maximized ("home")
  const [forceMini, setForceMini] = useState(false) // user clicked minimize (—) in Level 5
  const mini = (MINI_HOST && narrowWindow) || forceMini
  const phone = !mini && phoneWidth
  const [phoneTab, setPhoneTab] = useState('talk')
  const layoutRef = useRef({})
  layoutRef.current = { mini, phone, phoneTab }

  const handleMinimizeWindow = useCallback(() => {
    setWantFull(false)
    setForceMini(true)
    document.title = MINI_TITLE
    setWindowMode('mini').catch(() => {})
  }, [])

  const handleRestoreFullWindow = useCallback(() => {
    setForceMini(false)
    setWantFull(true)
    document.title = FULL_TITLE
    setWindowMode('maximize').catch(() => {})
  }, [])

  const handleToggleMaximize = useCallback(() => {
    setForceMini(false)
    setWantFull(true)
    document.title = FULL_TITLE
    setWindowMode('maximize').catch(() => {})
    try {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {})
      } else {
        document.documentElement.requestFullscreen?.().catch(() => {})
      }
    } catch {
      /* ignore */
    }
  }, [])
  const asleepRef = useRef(false)
  asleepRef.current = asleep
  const lastActive = useRef(Date.now())
  // { key, itemId, n }: the node (and item) the latest reply was about; n retriggers the animation
  const [focus, setFocus] = useState(null)
  const categoryKeys = useRef(new Set())
  const applyFocus = useCallback((f) => {
    if (!f?.node || !FOCUS_PREFIX[f.node] || !categoryKeys.current.has(f.node)) return
    const itemId = f.item != null ? `${FOCUS_PREFIX[f.node]}:${f.item}` : null
    setActiveKey(f.node)
    if (itemId) setSelectedId(itemId)
    setFocus({ key: f.node, itemId, n: Date.now() })
  }, [])

  const [speechPanel, setSpeechPanel] = useState(null)
  const speechPanelRef = useRef(speechPanel)
  speechPanelRef.current = speechPanel
  const speaker = useSpeaker()
  const {
    cancel,
    speaking,
    muted,
    voiceGender,
    rate,
    toggleMute,
    toggleVoiceGender,
    setVoiceGender,
    cycleRate,
    setRate,
  } = speaker
  const say = useCallback((...args) => {
    if (speechPanelRef.current !== 'meeting') speaker.say(...args)
  }, [speaker.say])

  // Persistent Global SSE Bridge for instant real-time Pub/Sub email push notifications
  useEffect(() => {
    const eventSource = new EventSource('/api/events')

    eventSource.onopen = () => {
      console.log('[SSE] Global stream connected to /api/events')
    }

    const handleIncomingNewEmail = (data) => {
      if (!data) return
      const idStr = String(data.id || data.row_id || Date.now())

      // Deduplicate if already handled
      if (prevEmailIdsRef.current.has(idStr)) return
      prevEmailIdsRef.current.add(idStr)

      setLatestSseEmail(data)

      const meta = getEmailDomainMeta(data.sender)
      const provider = meta?.brand || data.sender || 'Unknown Provider'
      const subject = data.subject || 'No Subject'
      const announcement = `You have new mail from ${provider}, subject: ${subject}.`

      // 1. Proactive Voice Announcement
      try {
        say(announcement)
      } catch (speechErr) {
        console.warn('[SpeechSynthesis] Announcement error:', speechErr)
      }

      // 2. Global UI Toast Notification
      const toastId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
      setEmailToasts((prev) => [
        ...prev,
        {
          id: toastId,
          provider,
          subject,
          sender: data.sender,
          category: data.category || 'Priority',
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ])
      setTimeout(() => {
        setEmailToasts((prev) => prev.filter((t) => t.id !== toastId))
      }, 8000)
    }

    eventSource.addEventListener('new_email', (event) => {
      try {
        const payload = JSON.parse(event.data)
        handleIncomingNewEmail(payload)
      } catch (err) {
        console.warn('[SSE] Failed to parse new_email event:', err)
      }
    })

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload?.type === 'new_email') {
          handleIncomingNewEmail(payload)
        } else if (payload?.type === 'turn_status') {
          if (payload.status === 'working') {
            setWorkingTarget(payload.target || 'agy')
            setBusy(true)
          } else if (payload.status === 'idle') {
            setWorkingTarget(null)
          }
        }
      } catch (err) {
        // ping or non-json comment
      }
    }

    eventSource.onerror = (err) => {
      console.warn('[SSE] Global EventSource connection error / reconnecting:', err)
    }

    return () => {
      eventSource.close()
    }
  }, [])

  const busyRef = useRef(false)
  const pendingRef = useRef(null)
  const lockedRef = useRef(false)
  const tabRef = useRef(panelTab)
  const rateRef = useRef(rate)
  busyRef.current = busy
  pendingRef.current = pending
  lockedRef.current = locked
  tabRef.current = panelTab
  rateRef.current = rate

  const add = useCallback((role, text, extra = {}) => {
    setEntries((prev) => [...prev, { id: nextId++, role, text, createdAt: performance.now(), ...extra }])
    if (tabRef.current !== 'log') setUnread((n) => n + 1)
  }, [])

  const refreshStatus = useCallback(() => {
    return getStatus()
      .then((s) => {
        setStatus(s)
        setLocked(false)
      })
      .catch((err) => {
        setStatus(null)
        if (err instanceof AuthError) setLocked(true)
      })
      .finally(() => setBootLoaded(true))
  }, [])

  useEffect(() => {
    refreshStatus()
  }, [refreshStatus])

  const offline = bootLoaded && !status && !locked
  useEffect(() => {
    if (!offline) return
    const id = setInterval(refreshStatus, 10_000)
    return () => clearInterval(id)
  }, [offline, refreshStatus])

  const finishBoot = useCallback(() => setBootDone(true), [])

  useEffect(() => {
    document.title = (MINI_HOST && !wantFull) || forceMini ? MINI_TITLE : FULL_TITLE
  }, [wantFull, forceMini])
  const wasNarrow = useRef(narrowWindow)
  useEffect(() => {
    if (MINI_HOST && narrowWindow && !wasNarrow.current) setWantFull(false) // the shortcut shrank it
    wasNarrow.current = narrowWindow
  }, [narrowWindow])

  const handleLogin = useCallback(
    async (e) => {
      e.preventDefault()
      const pin = pinInput.trim()
      if (!pin) return
      setPinError('')
      setBusy(true)
      try {
        await loginPin(pin)
        setPinInput('')
        setLocked(false)
        refreshStatus()
      } catch (err) {
        setPinError(err.message || 'That PIN didnâ€™t work.')
      } finally {
        setBusy(false)
      }
    },
    [pinInput, refreshStatus],
  )

  const handleLogout = useCallback(async () => {
    await logoutSession().catch(() => {})
    setStatus(null)
    setLocked(true)
  }, [])

  useEffect(() => {
    if (!busy) return
    setElapsed(0)
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [busy])

  const switchTab = useCallback((tab) => {
    tabRef.current = tab
    setPanelTab(tab)
    if (tab === 'log') setUnread(0)
  }, [])

  // /clear, /new, and the "new session" voice command: wipe the screen and the backend's memory
  const clearConversation = useCallback(() => {
    cancel()
    setEntries([])
    setUnread(0)
    resetSession().catch(() => {})
  }, [cancel])

  const asideRef = useRef(null)
  const revealPanel = useCallback(() => {
    if (!stacked()) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    asideRef.current?.scrollIntoView({ block: 'start', behavior: reduced ? 'auto' : 'smooth' })
  }, [])

  const submit = useCallback(
    async (text) => {
      let clean = text.trim()
      if (pendingRef.current) {
        if (/^(?:approve|confirm|yes|send)(?:\s+(?:the\s+)?(?:team\s+)?(?:reminder\s+)?email)?$/i.test(clean)) {
          approve()
          return
        }
        if (/^(?:decline|cancel|no|deny)(?:\s+(?:the\s+)?(?:team\s+)?(?:reminder\s+)?email)?$/i.test(clean)) {
          deny()
          return
        }
        return
      }
      if (!clean || busyRef.current || lockedRef.current) return

      // typed slash commands are handled here and never reach the backend as chat
      if (clean.startsWith('/')) {
        const cmd = clean.split(/\s+/)[0].toLowerCase()
        if (cmd === '/help') return setHelpOpen(true)
        if (cmd === '/voice' || cmd === '/meeting' || cmd === '/transcribe') {
          if (status?.role === 'readonly') return
          cancel()
          return setSpeechPanel(cmd === '/voice' ? 'voice' : 'meeting')
        }
        if (cmd === '/emails' || cmd === '/priority') {
          setTeamProgressTab('emails')
          setTeamProgressOpen(true)
          return
        }
        if (cmd === '/defense' || cmd === '/rehearsal') {
          setDefenseOpen(true)
          return
        }
        if (cmd === '/cockpit' || cmd === '/telemetry') {
          clean = 'system telemetry'
        } else if (cmd === '/timeline' || cmd === '/team') {
          clean = 'show team progress'
        }
        if (cmd === '/clear' || cmd === '/new') {
          clearConversation()
          switchTab('log')
          return
        }
        if (cmd === '/db') return setDbOpen(true)
        if (cmd === '/settings') return setSettingsOpen(true)
        if (cmd === '/review') {
          getRouterReview()
            .then((data) => {
              if (!data.misses || data.misses.length === 0) {
                add('nightmare', 'No pending router misses in the review queue.')
              } else {
                const lines = data.misses.map(
                  (m) => `#${m.id}: "${m.utterance}" -> nearest: ${m.nearest_intent} (${(m.similarity_score * 100).toFixed(1)}%)`
                )
                add('nightmare', `Router Miss Queue (${data.misses.length} pending):\n` + lines.join('\n'))
              }
            })
            .catch((err) => add('system', `Failed to load review queue: ${err.message}`))
          return
        }
        if (cmd === '/reminders') {
          clean = 'what are my reminders'
        } else if (cmd === '/sleep') {
          clean = 'go to sleep'
        } else {
          switchTab('log')
          add('system', `Unknown command ${cmd}. Type /help to see every command.`)
          return
        }
      }

      cancel()
      switchTab('log')
      add('you', clean)
      // on the phone, an action from a project page is answered on the Talk tab
      if (layoutRef.current.phone && layoutRef.current.phoneTab === 'projects') setPhoneTab('talk')

      // "open helper function" / "developer helper": open the helper UI with voice announcement
      if (HELPER_CMD_RE.test(clean)) {
        const msg = 'Opening developer helper function.'
        add('nightmare', msg, { ok: true, understood: 'quick_reply â†’ helper' })
        say(msg)
        setHelpOpen(true)
        return
      }

      // "home" / "mini": switch between the small window and the full view, no model call
      if (HOME_RE.test(clean) || MINI_RE.test(clean)) {
        const home = HOME_RE.test(clean)
        let msg
        if (home) {
          msg = layoutRef.current.mini ? 'Opening the full view.' : 'You’re already on the full view.'
          handleRestoreFullWindow()
        } else {
          msg = layoutRef.current.mini ? 'This is the small window.' : 'Back to the small window.'
          handleMinimizeWindow()
        }
        add('nightmare', msg, { ok: true, understood: home ? 'view → full' : 'view → mini' })
        say(msg)
        return
      }

      // sleep and wake are handled right here: instant, and they cost no model calls
      if (WAKE_RE.test(clean)) {
        const msg = asleepRef.current ? GREETING : "I'm already awake. What are we going to do today?"
        setAsleep(false)
        add('nightmare', msg, { ok: true, understood: 'wake_up' })
        say(msg)
        return
      }
      if (SLEEP_RE.test(clean)) {
        const msg = `Going to sleep. ${HOLD} and say â€œNightmare, wake upâ€ when you need me.`
        add('nightmare', msg, { ok: true, understood: 'sleep' })
        say(msg)
        setAsleep(true)
        return
      }
      setAsleep(false) // any other command wakes the graph up too

      // Local voice gender & speed commands
      const mVoice = VOICE_CMD_RE.exec(clean)
      if (mVoice) {
        const g = (mVoice.groups.g1 || mVoice.groups.g2 || mVoice.groups.gender).toLowerCase()
        setVoiceGender(g)
        const msg = `Switched to ${g} voice.`
        add('nightmare', msg, { ok: true, understood: `voice_settings â†’ ${g}` })
        say(msg, { gender: g })
        return
      }
      if (SPEED_FASTER_RE.test(clean)) {
        const next = Math.min(1.5, Number((rateRef.current + 0.15).toFixed(2)))
        setRate(next)
        const msg = `Reading speed set to ${next}x.`
        add('nightmare', msg, { ok: true, understood: `voice_settings â†’ ${next}x` })
        say(msg, { rate: next })
        return
      }
      if (SPEED_SLOWER_RE.test(clean)) {
        const next = Math.max(0.85, Number((rateRef.current - 0.15).toFixed(2)))
        setRate(next)
        const msg = `Reading speed set to ${next}x.`
        add('nightmare', msg, { ok: true, understood: `voice_settings â†’ ${next}x` })
        say(msg, { rate: next })
        return
      }
      if (SPEED_NORMAL_RE.test(clean)) {
        setRate(1.0)
        const msg = 'Reading speed reset to 1x.'
        add('nightmare', msg, { ok: true, understood: 'voice_settings â†’ 1x' })
        say(msg, { rate: 1.0 })
        return
      }

      setBusy(true)
      setWorkingTarget('processing')
      const t0 = performance.now()
      let focusAfter = null
      try {
        const res = await sendChat(clean)
        focusAfter = res.focus
        setHistory((h) => [...h.slice(-59), { ms: performance.now() - t0 }])
        let link
        if (res.ui === 'open_url' && res.url) {
          const opened = openInBrowser(res.url)
          link = { url: res.url, blocked: !opened }
        } else if (res.url) {
          link = { url: res.url, label: 'Visit Portfolio' }
        }
        if (res.ui === 'clear') setEntries([]) // "new session" by voice; the backend already forgot
        add('nightmare', res.reply, { ok: res.ok, understood: res.understood, focus: res.focus, link })
        if (stacked()) {
          switchTab('log') // on a phone, show the answer instead of an unread badge far below
          revealPanel()
        }
        if (res.needs_confirm) setPending({ id: res.pending_id, label: res.action_label })
        if (res.ui === 'db_pin') setDbOpen(true)
        if (res.ui === 'db_close') setDbOpen(false)
        if (res.ui === 'settings_pin') setSettingsOpen(true)
        if (res.ui?.startsWith('voice:')) setVoiceGender(res.ui.split(':')[1])
        if (res.ui === 'settings_close') setSettingsOpen(false)
        if (res.ui === 'help') setHelpOpen(true)
        if (res.ui === 'team_progress') {
          setTeamProgressData(res.data)
          setTeamProgressTab('summary')
          setTeamProgressOpen(true)
        }
        if (res.ui === 'team_progress:diff') {
          setTeamProgressData(res.data)
          setTeamProgressTab('diff')
          setTeamProgressOpen(true)
        }
        if (res.ui === 'team_progress:emails' || res.ui === 'team_progress:inbox' || res.ui === 'email_report') {
          setTeamProgressData(res.data)
          setTeamProgressTab('emails')
          setTeamProgressOpen(true)
        }
        if (res.ui?.startsWith('defense:')) {
          setDefenseData(res.data)
          setDefenseOpen(true)
        }
        // Always read the full generated reply aloud
        say(res.reply)
      } catch (err) {
        if (err instanceof AuthError) setLocked(true)
        add('system', err.message)
      } finally {
        setBusy(false)
        setWorkingTarget(null)
        // light the node up only after fresh counts arrive, so a new reminder is already on the arc
        refreshStatus().then(() => applyFocus(focusAfter))
      }
    },
    [
      add,
      cancel,
      say,
      refreshStatus,
      switchTab,
      setVoiceGender,
      setRate,
      clearConversation,
      applyFocus,
      revealPanel,
      status?.role,
    ],
  )

  // ---- idle sleep ----
  // Clicks, keys and the wheel count as activity, and so does anything Nightmare is doing.
  useEffect(() => {
    const mark = () => {
      lastActive.current = Date.now()
    }
    const events = ['pointerdown', 'keydown', 'wheel']
    events.forEach((e) => window.addEventListener(e, mark, { passive: true }))
    return () => events.forEach((e) => window.removeEventListener(e, mark))
  }, [])
  useEffect(() => {
    lastActive.current = Date.now()
  }, [busy, speaking, pending, entries])
  useEffect(() => {
    const id = setInterval(() => {
      const occupied = asleepRef.current || busyRef.current || pendingRef.current || lockedRef.current
      if (occupied || dbOpen || settingsOpen || helpOpen || speechPanel || speaking || offline) return
      if (Date.now() - lastActive.current > SLEEP_AFTER_MS) setAsleep(true)
    }, 5000)
    return () => clearInterval(id)
  }, [dbOpen, settingsOpen, helpOpen, speechPanel, speaking, offline])

  const decide = useCallback(
    async (approve) => {
      const item = pendingRef.current
      if (!item) return
      pendingRef.current = null
      setPending(null)
      setBusy(true)
      try {
        const res = await confirmAction(item.id, approve)
        add('nightmare', res.reply, { ok: res.ok })
        say(res.reply)
      } catch (err) {
        if (err instanceof AuthError) setLocked(true)
        add('system', err.message)
      } finally {
        setBusy(false)
        refreshStatus()
      }
    },
    [add, say, refreshStatus],
  )
  const approve = useCallback(() => decide(true), [decide])
  const deny = useCallback(() => decide(false), [decide])

  const { listening, interim, error: speechError, lang, toggleLang, start: recStart, stop: recStop, cancel: recCancel, supported } =
    useRecognizer({ onFinal: (text) => { if (!speechPanelRef.current) submit(text) } })

  useEffect(() => {
    if (speechPanel) { recCancel(); cancel() }
  }, [speechPanel, recCancel, cancel])

  const press = useCallback(() => {
    if (speechPanelRef.current) return
    if (busyRef.current || pendingRef.current || lockedRef.current) return
    cancel()
    recStart()
  }, [cancel, recStart])
  const release = useCallback(() => recStop(), [recStop])

  useEffect(() => {
    const down = (e) => {
      if (e.code !== 'Space' || e.repeat || ownsSpace(e.target)) return
      e.preventDefault()
      press()
    }
    const up = (e) => {
      if (e.code !== 'Space' || ownsSpace(e.target)) return
      e.preventDefault()
      release()
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', release)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', release)
    }
  }, [press, release])

  const categories = useMemo(() => buildCategories(status), [status])
  categoryKeys.current = new Set(categories.map((c) => c.key))
  const selectedItem = useMemo(() => {
    for (const cat of categories) {
      const found = cat.items.find((i) => i.id === selectedId)
      if (found) return found
    }
    return null
  }, [categories, selectedId])

  const readonly = status?.role === 'readonly'
  const disabled = busy || Boolean(pending)
  const canTalk = supported && !disabled && !offline

  const handleSelect = useCallback(
    (item) => {
      setSelectedId(item.id)
      switchTab('details')
      revealPanel()
    },
    [switchTab, revealPanel],
  )

  const handleActivate = useCallback(
    (item) => {
      const act = item.actions.find((a) => !(readonly && a.full))
      if (act) submit(act.command)
    },
    [readonly, submit],
  )

  const mode = offline
    ? 'offline'
    : pending
      ? 'confirm'
      : busy
        ? 'thinking'
        : listening
          ? 'listening'
          : asleep
            ? 'sleep'
            : speaking
              ? 'speaking'
              : 'idle'

  const [title, caption, caption2] = {
    sleep: ['Sleeping', `${HOLD} and say â€œNightmare, wake upâ€`, 'Idle'],
    offline: ['Asleep', 'Backend offline', 'Start it with python -m backend'],
    confirm: ['Awaiting you', 'Approve or deny with a click', null],
    thinking: ['Thinking', `${elapsed}s so far`, 'Fast model ~8s Â· Smart model ~14s'],
    listening: ['Listening', interim || 'Speak now, release to send', null],
    speaking: ['Speaking', `${voiceGender} voice · ${rate}x`, TOUCH ? 'Tap Stop to interrupt' : 'Hold Space or click Stop to interrupt'],
    idle: supported
      ? ['Watching', TOUCH ? 'Hold the eye to talk' : 'Hold the eye or Space to talk', null]
      : ['Watching', 'Type a command in the panel', 'Voice input needs Chrome or Edge'],
  }[mode]

  const lastAsked = useMemo(() => entries.findLast((e) => e.role === 'you')?.text, [entries])
  const lastAnswer = useMemo(() => entries.findLast((e) => e.role !== 'you'), [entries])

  const composerProps = {
    disabled: disabled || offline,
    onSubmit: submit,
    listening,
    micSupported: supported,
    canTalk,
    onPressStart: press,
    onPressEnd: release,
    lang,
    onToggleLang: toggleLang,
    muted,
    onToggleMute: toggleMute,
    voiceGender,
    onToggleVoiceGender: toggleVoiceGender,
    rate,
    onCycleRate: cycleRate,
    speaking,
    onStopSpeaking: cancel,
    speechError,
  }
  const talkProps = {
    mode,
    title,
    caption,
    canTalk,
    onPressStart: press,
    onPressEnd: release,
    answer: lastAnswer,
    asked: lastAsked,
    busy,
    elapsed,
    speaking,
    onSpeak: say,
    onStop: cancel,
  }

  return (
    <div
      data-clearance="5"
      className="relative flex h-dvh flex-col overflow-hidden transition-colors duration-700"
    >
      <Background />
      {!mini && (phone || locked) && (
        <StatusBar
          status={status}
          locked={locked}
          lastAsked={lastAsked}
          busy={busy}
          workingTarget={workingTarget}
          elapsed={elapsed}
          onLogout={handleLogout}
          onRetry={refreshStatus}
          onSettings={() => setSettingsOpen(true)}
          onOpenEmails={() => {
            setTeamProgressTab('emails')
            setTeamProgressOpen(true)
          }}
          onOpenDefense={() => setDefenseOpen(true)}
          onOpenTelemetry={() => submit('system telemetry')}
        />
      )}

      {locked ? (
        <LockScreen pin={pinInput} setPin={setPinInput} error={pinError} busy={busy} onSubmit={handleLogin} />
      ) : mini ? (
        <div className={forceMini && !narrowWindow ? 'm-auto flex h-[560px] w-[400px] max-w-full flex-col overflow-hidden rounded-2xl border border-[#ff2a4b]/60 bg-[#0b0204]/95 shadow-[0_0_50px_rgba(220,20,60,0.4)]' : 'flex min-h-0 flex-1 flex-col'}>
          <MiniView
            {...talkProps}
            status={status}
            offline={offline}
            onHome={handleRestoreFullWindow}
            composer={composerProps}
          />
        </div>
      ) : phone ? (
        <PhoneView
          tab={phoneTab}
          onTab={setPhoneTab}
          categories={categories}
          entries={entries}
          unread={unread}
          readonly={readonly}
          disabled={disabled}
          onRun={submit}
          talk={talkProps}
          composer={composerProps}
          busy={busy}
          elapsed={elapsed}
          onSpeak={say}
        />
      ) : (
        <Level5View
          disabled={disabled || offline}
          speechError={speechError}
          status={status}
          categories={categories}
          activeKey={activeKey}
          onCategory={setActiveKey}
          selectedId={selectedId}
          selectedItem={selectedItem}
          onSelect={(item) => setSelectedId(item ? item.id : null)}
          onActivate={handleActivate}
          mode={mode}
          title={title}
          caption={caption}
          caption2={caption2}
          focus={focus}
          asleep={asleep}
          bootDone={bootDone}
          entries={entries}
          busy={busy}
          workingTarget={workingTarget}
          elapsed={elapsed}
          listening={listening}
          interim={interim}
          speaking={speaking}
          canTalk={canTalk}
          speechProgress={speaker.speechProgress}
          onPressStart={press}
          onPressEnd={release}
          onSubmit={submit}
          onSpeak={say}
          onStopSpeaking={cancel}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenDb={() => setDbOpen(true)}
          onOpenHelp={() => setHelpOpen(true)}
          onOpenDefense={() => setDefenseOpen(true)}
          onOpenTeamTimeline={() => submit('show team progress')}
          onOpenEmails={() => {
            setTeamProgressTab('emails')
            setTeamProgressOpen(true)
          }}
          onOpenTelemetry={() => submit('system telemetry')}
          onMinimizeWindow={handleMinimizeWindow}
          onToggleMaximize={handleToggleMaximize}
        />
      )}

      {pending && <ConfirmDialog action={pending} onApprove={approve} onDeny={deny} />}
      {speechPanel && !locked && !readonly && <SpeechPanel mode={speechPanel} speaker={speaker} onClose={() => { cancel(); setSpeechPanel(null) }} />}
      {dbOpen && !locked && <DatabasePanel onClose={closeDbPanel} />}
      {settingsOpen && !locked && !readonly && <SettingsPanel onClose={closeSettingsPanel} />}
      {helpOpen && !locked && (
        <HelpPanel
          onClose={closeHelp}
          onRun={(command) => {
            setHelpOpen(false)
            submit(command)
          }}
        />
      )}
      {teamProgressOpen && !locked && (
        <TeamProgressPanel
          data={teamProgressData}
          initialTab={teamProgressTab}
          pendingAction={pending}
          onApprove={approve}
          onDecline={deny}
          onClose={closeTeamProgress}
          onRefresh={() => submit('show team progress')}
          incomingEmail={latestSseEmail}
        />
      )}
      {/* GLOBAL PROACTIVE EMAIL TOAST NOTIFICATION CONTAINER */}
      {emailToasts.length > 0 && (
        <div className="fixed top-16 right-6 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
          {emailToasts.map((toast) => (
            <aside
              key={toast.id}
              role="status"
              aria-live="polite"
              className="pointer-events-auto flex items-start gap-3 p-3.5 rounded-xl border border-amber-400/90 bg-[#160408]/98 backdrop-blur-md text-bone shadow-[0_0_30px_rgba(245,158,11,0.35)] animate-fadeIn transition cursor-pointer hover:border-amber-300"
              onClick={() => {
                setTeamProgressTab('emails')
                setTeamProgressOpen(true)
                dismissEmailToast(toast.id)
              }}
            >
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-crimson/30 border border-crimson/60 text-amber-300 shadow-[0_0_10px_rgba(220,38,38,0.3)]">
                <Icon name="mail" className="h-4 w-4 text-amber-400" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-mono font-bold text-amber-300 uppercase tracking-wider">
                    NEW EMAIL ARRIVED • {toast.category ? toast.category.toUpperCase() : 'PRIORITY'}
                  </span>
                  <span className="text-[10px] font-mono text-ash">{toast.time}</span>
                </div>
                <h4 className="text-xs font-bold text-bone truncate mt-0.5" title={toast.subject}>
                  {toast.subject}
                </h4>
                <p className="text-[11px] font-mono text-ash truncate">
                  From: <strong className="text-amber-200">{toast.provider}</strong> ({toast.sender})
                </p>
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  dismissEmailToast(toast.id)
                }}
                className="text-ash hover:text-white text-xs px-1 hover:bg-scar/30 rounded"
                title="Dismiss notification"
              >
                ✕
              </button>
            </aside>
          ))}
        </div>
      )}
      <DefensePanel
        open={defenseOpen && !locked}
        data={defenseData}
        status={status}
        onClose={closeDefense}
        onCommand={(cmd) => submit(cmd)}
      />
      {!bootDone && <Boot done={bootLoaded} onFinished={finishBoot} />}
    </div>
  )
}
