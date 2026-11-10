import { useEffect, useRef, useState, useCallback } from 'react'
import gsap from 'gsap'
import Icon from './Icon'
import { Level5EyeLogo } from './Level5View'
import {
  openTimelineInExcel,
  syncTimelineBaseline,
  getTimelineDiff,
  getPriorityEmails,
  updateEmailStatus,
  getCalendarEvents,
  createCalendarEvent,
  getMeasurableTasks,
  updateMeasurableTask,
} from '../api'

const GDRIVE_URL =
  'https://docs.google.com/spreadsheets/d/1Kw4_zboMzpv2WKdJHeNVuSYSfW4Gg_xm/edit?usp=drive_link&ouid=109543692766011182977&rtpof=true&sd=true'

const FALLBACK_ROADMAP_STAGES = [
  {
    stage_id: 'STG-01',
    stage_name: 'Stage 1',
    calendar_span: 'Aug – Sep 2026',
    phase: 'Phase 1',
    title: 'Topic Formulation & Adviser Alignment',
    activities: 'Select research topic, align with adviser, define scope (Pasig City), and formulate study objectives.',
    milestone: 'Approved Topic & Concept Note',
    status: 'Completed',
    progress_pct: 100,
    short_label: 'Topic Formulation',
  },
  {
    stage_id: 'STG-02',
    stage_name: 'Stage 2',
    calendar_span: 'Sep – Oct 2026',
    phase: 'Phase 1',
    title: 'Literature Review (RRL) & Synthesis',
    activities: 'Review ≥50 peer-reviewed studies (2021–2026) on GNNs, NLP, XAI, and e-governance; build gap matrix.',
    milestone: 'Completed Chapter 2 & Synthesis Matrix',
    status: 'Completed',
    progress_pct: 100,
    short_label: 'Literature Review',
  },
  {
    stage_id: 'STG-03',
    stage_name: 'Stage 3',
    calendar_span: 'Oct – Nov 2026',
    phase: 'Phase 1',
    title: 'System Design & Methodology Formulation',
    activities: 'Design CitizenGraph 6-stage pipeline, heterogeneous graph schema, mathematical formulations, and evaluation metrics.',
    milestone: 'Completed Chapter 1 & Chapter 3 Drafts',
    status: 'In Progress',
    progress_pct: 60,
    short_label: 'System Design',
  },
  {
    stage_id: 'STG-04',
    stage_name: 'Stage 4',
    calendar_span: 'Nov – Dec 2026 (2nd Wk)',
    phase: 'Phase 1',
    title: 'Chapters 1–3 Finalization & Proposal Defense',
    activities: 'Adviser manuscript review, revisions, deck preparation, and formal Thesis Proposal Defense.',
    milestone: '★ MILESTONE: Ch 1–3 Submitted & Defended (2nd Wk Dec)',
    status: 'Pending',
    progress_pct: 0,
    short_label: 'Proposal Defense',
  },
  {
    stage_id: 'STG-05',
    stage_name: 'Stage 5',
    calendar_span: 'Dec 2026 – Jan 2027',
    phase: 'Phase 1 / 2',
    title: 'Ethics Clearance, FOI & LGU Data Acquisition',
    activities: 'Secure Ethics/Data Privacy clearance, submit FOI requests, and collect Pasig City public complaint records.',
    milestone: 'Approved Permits & Raw Complaint Dataset',
    status: 'Pending',
    progress_pct: 0,
    short_label: 'Ethics & Data Acq.',
  },
  {
    stage_id: 'STG-06',
    stage_name: 'Stage 6',
    calendar_span: 'Jan – Feb 2027',
    phase: 'Phase 2',
    title: 'Corpus Annotation & Core Pipeline Development',
    activities: 'Clean/anonymize records, annotate dataset (κ ≥ 0.80), fine-tune XLM-RoBERTa, and build Heterogeneous Graph + GATv2.',
    milestone: 'Trained NLP + GATv2 Core & Verified Graph DB',
    status: 'Pending',
    progress_pct: 0,
    short_label: 'Corpus & Core Dev',
  },
  {
    stage_id: 'STG-07',
    stage_name: 'Stage 7',
    calendar_span: 'Feb 2027',
    phase: 'Phase 2',
    title: 'XAI Integration, Dashboard & Empirical Evaluation',
    activities: 'Integrate GNNExplainer + LLM rationale, build Next.js/FastAPI dashboard, run ablation & ISO/IEC 25010 evaluation.',
    milestone: '★ MILESTONE: Full Prototype & Evaluation Complete (Feb)',
    status: 'Pending',
    progress_pct: 0,
    short_label: 'XAI & Evaluation',
  },
  {
    stage_id: 'STG-08',
    stage_name: 'Stage 8',
    calendar_span: 'Feb – Mar 2027',
    phase: 'Phase 2',
    title: 'Chapters 4–5 Writing & Manuscript Polish',
    activities: 'Write Chapter 4 (Results & Discussion) and Chapter 5 (Summary, Conclusions, Recommendations); plagiarism & grammar check.',
    milestone: 'Complete Chapters 1–5 Final Manuscript',
    status: 'Pending',
    progress_pct: 0,
    short_label: 'Chapters 4–5 Writing',
  },
  {
    stage_id: 'STG-09',
    stage_name: 'Stage 9',
    calendar_span: 'Mar 2027',
    phase: 'Phase 2',
    title: 'Final Oral Defense & Hardbound Submission',
    activities: 'Conduct mock defense, defend final thesis before panel, apply final revisions, and submit hardbound copies.',
    milestone: '★ MILESTONE: Passed Final Oral Defense & Bound Copy',
    status: 'Pending',
    progress_pct: 0,
    short_label: 'Final Oral Defense',
  },
]

const FALLBACK_PRIORITY_TASKS = [
  { id: 'pt-1', title: 'Complete system architecture', date: 'Jan 20, 2027', priority: 'High', phase: 'Phase 1', status: 'In Progress' },
  { id: 'pt-2', title: 'Finish data collection', date: 'Jan 25, 2027', priority: 'High', phase: 'Phase 1', status: 'In Progress' },
  { id: 'pt-3', title: 'Draft Chapter 4', date: 'Feb 5, 2027', priority: 'Medium', phase: 'Phase 2', status: 'Pending' },
  { id: 'pt-4', title: 'Prepare for evaluation', date: 'Feb 10, 2027', priority: 'Medium', phase: 'Phase 2', status: 'Pending' },
]

function StatusBadge({ status }) {
  const norm = (status || 'Pending').toLowerCase()
  if (norm.includes('complete') || norm.includes('done') || norm === 'read') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-mono font-bold tracking-wide border border-[#22c55e] bg-[rgba(22,163,74,0.18)] text-[#4ade80] shadow-[0_0_10px_rgba(34,197,94,0.15)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#4ade80]" />
        {status?.toUpperCase() || 'COMPLETED'}
      </span>
    )
  }
  if (norm.includes('progress') || norm.includes('active') || norm.includes('ongoing')) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-mono font-bold tracking-wide border border-[#f97316] bg-[rgba(234,88,12,0.18)] text-[#fdba74] shadow-[0_0_10px_rgba(249,115,22,0.15)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#f97316] animate-pulse" />
        IN PROGRESS
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-mono font-bold tracking-wide border border-[#ef4444] bg-[rgba(220,38,38,0.18)] text-[#fca5a5] shadow-[0_0_10px_rgba(239,68,68,0.15)]">
      <span className="h-1.5 w-1.5 rounded-full bg-[#ef4444]" />
      PENDING
    </span>
  )
}

export function getEmailDomainMeta(sender = '') {
  const s = sender.toLowerCase()
  if (s.includes('vercel')) {
    return {
      brand: 'VERCEL',
      domain: 'vercel.com',
      badgeClass: 'border-white/60 bg-white/10 text-white shadow-[0_0_10px_rgba(255,255,255,0.15)]',
      icon: '▲',
      isPerson: false,
    }
  }
  if (s.includes('supabase')) {
    return {
      brand: 'SUPABASE',
      domain: 'supabase.io',
      badgeClass: 'border-emerald-500/60 bg-emerald-950/40 text-emerald-300 shadow-[0_0_10px_rgba(16,185,129,0.15)]',
      icon: '⚡',
      isPerson: false,
    }
  }
  if (s.includes('anthropic')) {
    return {
      brand: 'ANTHROPIC',
      domain: 'anthropic.com',
      badgeClass: 'border-amber-400/60 bg-amber-950/40 text-amber-300 shadow-[0_0_10px_rgba(251,191,36,0.2)]',
      icon: '✦',
      isPerson: false,
    }
  }
  if (s.includes('google')) {
    return {
      brand: 'GOOGLE',
      domain: 'google.com',
      badgeClass: 'border-sky-400/60 bg-sky-950/40 text-sky-300 shadow-[0_0_10px_rgba(56,189,248,0.2)]',
      icon: 'G',
      isPerson: false,
    }
  }
  if (s.includes('render')) {
    return {
      brand: 'RENDER',
      domain: 'render.com',
      badgeClass: 'border-indigo-400/60 bg-indigo-950/40 text-indigo-300 shadow-[0_0_10px_rgba(129,140,248,0.2)]',
      icon: '■',
      isPerson: false,
    }
  }

  // Personal Email Detection (e.g. "Garcia Sabar <garciasabar12@gmail.com>")
  let cleanDomain = 'direct'
  if (s.includes('@')) {
    const afterAt = s.split('@')[1] || ''
    cleanDomain = afterAt.replace(/[>]/g, '').trim()
  }

  let personName = ''
  if (sender.includes('<')) {
    personName = sender.split('<')[0].replace(/["']/g, '').trim()
  } else if (!sender.includes('@')) {
    personName = sender.trim()
  }

  return {
    brand: personName ? personName.toUpperCase() : 'PERSON / DIRECT',
    domain: cleanDomain,
    badgeClass: 'border-amber-400/70 bg-gradient-to-r from-amber-500/20 to-crimson/25 text-amber-200 shadow-[0_0_12px_rgba(251,191,36,0.25)]',
    icon: '👤',
    isPerson: true,
  }
}

export default function TeamProgressPanel({
  data,
  initialTab = 'summary',
  pendingAction,
  onApprove,
  onDecline,
  onClose,
  onRefresh,
  incomingEmail = null,
}) {
  const panelRef = useRef(null)
  const contentRef = useRef(null)

  const [activeTab, setActiveTab] = useState(
    initialTab === 'diff' ? 'diff' : (initialTab === 'emails' || initialTab === 'inbox' ? 'emails' : 'summary')
  )
  const [roadmapFilter, setRoadmapFilter] = useState('ALL')
  const [wbsPhaseFilter, setWbsPhaseFilter] = useState('ALL')
  const [wbsStatusFilter, setWbsStatusFilter] = useState('ALL')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedStageId, setSelectedStageId] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [busyAction, setBusyAction] = useState(false)

  // Real-Time Priority Email Feed States & Category Views
  const [priorityEmails, setPriorityEmails] = useState([])
  const [isSyncingEmails, setIsSyncingEmails] = useState(false)
  const [lastEmailSync, setLastEmailSync] = useState(null)
  const [showEmailOverlay, setShowEmailOverlay] = useState(false)
  const [emailDomainFilter, setEmailDomainFilter] = useState('ALL')
  const [emailStatusFilter, setEmailStatusFilter] = useState('ALL')
  const [selectedCategory, setSelectedCategory] = useState('priority')
  const [emailActionBusyId, setEmailActionBusyId] = useState(null)
  const [toasts, setToasts] = useState([])

  const prevEmailIdsRef = useRef(null)
  const selectedCategoryRef = useRef(selectedCategory)
  selectedCategoryRef.current = selectedCategory

  // Proactive Voice Announcement & Toast Notification Helper
  const triggerEmailNotification = useCallback((email, catFallback = null) => {
    const meta = getEmailDomainMeta(email.sender)
    const provider = meta?.brand || email.sender || 'Unknown Provider'
    const subject = email.subject || 'No Subject'
    const announcement = `You have new mail from ${provider}, subject: ${subject}.`

    // Proactive Voice Announcement via window.speechSynthesis
    try {
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel()
        const utterance = new SpeechSynthesisUtterance(announcement)
        utterance.rate = 1.0
        window.speechSynthesis.speak(utterance)
      }
    } catch (speechErr) {
      console.warn('[SpeechSynthesis] Announcement error:', speechErr)
    }

    // Proactive UI Toast Notification
    const toastId = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    setToasts((prev) => [
      ...prev,
      {
        id: toastId,
        provider,
        subject,
        sender: email.sender,
        category: email.category || catFallback || selectedCategoryRef.current,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toastId))
    }, 8000)
  }, [])

  // Silent sync fetcher with category filter and proactive announcement
  const fetchPriorityEmails = useCallback(async (silent = false, category = null) => {
    const catToFetch = category !== null ? category : selectedCategoryRef.current
    if (!silent) setIsSyncingEmails(true)
    try {
      const res = await getPriorityEmails(50, '', catToFetch)
      const list = Array.isArray(res) ? res : (res?.emails || [])
      setPriorityEmails(list)
      setLastEmailSync(new Date())

      // Track previous list of email IDs
      if (prevEmailIdsRef.current === null) {
        prevEmailIdsRef.current = new Set(list.map((e) => String(e.id || e.row_id)))
      } else {
        const newEmails = list.filter((e) => {
          const idStr = String(e.id || e.row_id)
          return !prevEmailIdsRef.current.has(idStr)
        })

        if (newEmails.length > 0) {
          newEmails.forEach((email) => {
            const idStr = String(email.id || email.row_id)
            prevEmailIdsRef.current.add(idStr)
            triggerEmailNotification(email, catToFetch)
          })
        }
      }
    } catch (err) {
      console.warn('[PriorityEmails] Silent background sync error:', err)
    } finally {
      if (!silent) setIsSyncingEmails(false)
    }
  }, [triggerEmailNotification])

  // Fail-safe initial sync on mount
  useEffect(() => {
    fetchPriorityEmails(false, selectedCategory)
  }, [fetchPriorityEmails, selectedCategory])

  // Reactive incoming email stream from root SSE bridge
  useEffect(() => {
    if (!incomingEmail) return
    const idStr = String(incomingEmail.id || incomingEmail.row_id || Date.now())

    if (prevEmailIdsRef.current && prevEmailIdsRef.current.has(idStr)) {
      return
    }
    if (!prevEmailIdsRef.current) {
      prevEmailIdsRef.current = new Set()
    }
    prevEmailIdsRef.current.add(idStr)

    // Instantly prepend to state
    setPriorityEmails((prev) => [
      {
        id: idStr,
        sender: incomingEmail.sender || 'Unknown Sender',
        subject: incomingEmail.subject || 'No Subject',
        category: incomingEmail.category || 'Priority',
        status: incomingEmail.status || 'Pending',
        row_id: incomingEmail.row_id || idStr,
      },
      ...prev.filter((e) => String(e.id || e.row_id) !== idStr),
    ])
    setLastEmailSync(new Date())
  }, [incomingEmail])

  // Standalone EventSource listener if incomingEmail prop is not provided by parent
  useEffect(() => {
    if (incomingEmail !== null) return // parent App.jsx is handling the global SSE stream

    const eventSource = new EventSource('/api/events')

    eventSource.onopen = () => {
      fetchPriorityEmails(false, selectedCategoryRef.current)
    }

    const handleIncomingEmail = (data) => {
      if (!data) return
      const idStr = String(data.id || data.row_id || Date.now())

      if (prevEmailIdsRef.current && prevEmailIdsRef.current.has(idStr)) {
        return
      }
      if (!prevEmailIdsRef.current) {
        prevEmailIdsRef.current = new Set()
      }
      prevEmailIdsRef.current.add(idStr)

      setPriorityEmails((prev) => [
        {
          id: idStr,
          sender: data.sender || 'Unknown Sender',
          subject: data.subject || 'No Subject',
          category: data.category || 'Priority',
          status: data.status || 'Pending',
          row_id: data.row_id || idStr,
        },
        ...prev.filter((e) => String(e.id || e.row_id) !== idStr),
      ])
      setLastEmailSync(new Date())

      triggerEmailNotification(data, selectedCategoryRef.current)
    }

    eventSource.addEventListener('new_email', (event) => {
      try {
        const payload = JSON.parse(event.data)
        handleIncomingEmail(payload)
      } catch (err) {
        console.warn('[SSE] Failed to parse new_email event:', err)
      }
    })

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload?.type === 'new_email') {
          handleIncomingEmail(payload)
        }
      } catch (err) {
        // ping or non-json comment
      }
    }

    eventSource.onerror = (err) => {
      console.warn('[SSE] EventSource connection error / reconnecting:', err)
    }

    return () => {
      eventSource.close()
    }
  }, [incomingEmail, fetchPriorityEmails, triggerEmailNotification])

  const handleSelectCategory = (cat) => {
    setSelectedCategory(cat)
    fetchPriorityEmails(false, cat)
  }

  const dismissToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  // Local Calendar & Measurable Tasks States
  const [calendarEvents, setCalendarEvents] = useState([])
  const [measurableTasks, setMeasurableTasks] = useState([])
  const [calFilter, setCalFilter] = useState('ALL')
  const [showEventForm, setShowEventForm] = useState(false)
  const [showTaskForm, setShowTaskForm] = useState(false)
  const [newEventTitle, setNewEventTitle] = useState('')
  const [newEventType, setNewEventType] = useState('meeting')
  const [newEventDate, setNewEventDate] = useState('')
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [newTaskTarget, setNewTaskTarget] = useState('')
  const [newTaskUnit, setNewTaskUnit] = useState('')

  const fetchCalendarAndTasks = useCallback(async () => {
    try {
      const [events, tasks] = await Promise.all([
        getCalendarEvents(),
        getMeasurableTasks(),
      ])
      setCalendarEvents(Array.isArray(events) ? events : [])
      setMeasurableTasks(Array.isArray(tasks) ? tasks : [])
    } catch (err) {
      console.warn('[CalendarTasks] fetch error:', err)
    }
  }, [])

  useEffect(() => {
    fetchCalendarAndTasks()
  }, [fetchCalendarAndTasks])

  const handleCreateEvent = async (e) => {
    e?.preventDefault()
    if (!newEventTitle.trim()) return
    try {
      const startIso = newEventDate
        ? new Date(newEventDate).toISOString()
        : new Date().toISOString()
      const res = await createCalendarEvent({
        title: newEventTitle.trim(),
        event_type: newEventType,
        start_date: startIso,
      })
      if (res?.ok && res.event) {
        setCalendarEvents((prev) => [res.event, ...prev])
        setNewEventTitle('')
        setNewEventDate('')
        setShowEventForm(false)
        setFeedback({ type: 'success', msg: `Added event: ${res.event.title}` })
      }
    } catch (err) {
      setFeedback({ type: 'error', msg: err.message || 'Failed to create event' })
    }
  }

  const handleCreateTask = async (e) => {
    e?.preventDefault()
    if (!newTaskTitle.trim()) return
    const tgt = parseInt(newTaskTarget, 10) || 1
    try {
      const res = await updateMeasurableTask({
        title: newTaskTitle.trim(),
        current_progress: 0,
        target_progress: tgt,
        unit: newTaskUnit.trim(),
      })
      if (res?.ok && res.task) {
        setMeasurableTasks((prev) => [...prev, res.task])
        setNewTaskTitle('')
        setNewTaskTarget('')
        setNewTaskUnit('')
        setShowTaskForm(false)
        setFeedback({ type: 'success', msg: `Created task: ${res.task.title}` })
      }
    } catch (err) {
      setFeedback({ type: 'error', msg: err.message || 'Failed to create task' })
    }
  }

  const handleAdjustTaskProgress = async (task, delta) => {
    const nextVal = Math.max(0, task.current_progress + delta)
    try {
      await updateMeasurableTask({
        title: task.title,
        current_progress: nextVal,
        target_progress: task.target_progress,
        unit: task.unit,
      })
      setMeasurableTasks((prev) =>
        prev.map((t) => (t.id === task.id ? { ...t, current_progress: nextVal } : t))
      )
    } catch (err) {
      console.error('Failed to update task:', err)
    }
  }

  const handleToggleEmailStatus = async (email) => {
    const nextStatus = (email.status || 'Pending').toLowerCase() === 'pending' ? 'Read' : 'Pending'
    setEmailActionBusyId(email.id)
    setPriorityEmails((prev) =>
      prev.map((e) => (e.id === email.id ? { ...e, status: nextStatus } : e))
    )
    try {
      await updateEmailStatus(email.id, nextStatus)
    } catch (err) {
      console.error('Failed to update email status:', err)
      fetchPriorityEmails(true)
    } finally {
      setEmailActionBusyId(null)
    }
  }

  // Sync initial tab when changed from props
  useEffect(() => {
    if (initialTab === 'diff') setActiveTab('diff')
    else if (initialTab === 'emails' || initialTab === 'inbox') setActiveTab('emails')
    else if (initialTab === 'calendar' || initialTab === 'tasks' || initialTab === 'calendar_tasks') setActiveTab('calendar_tasks')
    else if (initialTab === 'summary') setActiveTab('summary')
  }, [initialTab])

  // GSAP modal entrance
  useEffect(() => {
    if (panelRef.current) {
      gsap.fromTo(
        panelRef.current,
        { opacity: 0, scale: 0.98, y: 16 },
        { opacity: 1, scale: 1, y: 0, duration: 0.26, ease: 'power2.out' },
      )
    }
  }, [])

  // GSAP tab switch animation
  useEffect(() => {
    if (contentRef.current) {
      gsap.fromTo(
        contentRef.current,
        { opacity: 0, y: 8 },
        { opacity: 1, y: 0, duration: 0.2, ease: 'power2.out' },
      )
    }
  }, [activeTab])

  const rawRoadmap = data?.roadmap && data.roadmap.length > 0 ? data.roadmap : FALLBACK_ROADMAP_STAGES
  const roadmap = rawRoadmap.map((s, idx) => {
    const normStatus = (s.status || 'Pending').toLowerCase()
    const pct =
      s.progress_pct != null
        ? s.progress_pct
        : normStatus.includes('complete')
          ? 100
          : normStatus.includes('progress')
            ? Math.max(20, 42 - idx * 8)
            : 0
    return {
      ...s,
      progress_pct: pct,
      short_label: s.short_label || (s.title ? s.title.split('&')[0].trim().slice(0, 22) : s.stage_id),
    }
  })
  const wbs = data?.wbs || []
  const objectives = data?.objectives || []
  const dashboard = data?.dashboard || {}
  const diff = data?.diff || {}
  const gdriveInfo = data?.gdrive_info || {}
  const gdriveUrl = gdriveInfo?.folder_url || GDRIVE_URL
  const quotas = data?.quotas || []
  const staleTasks = data?.stale_tasks || []
  const fileName = data?.file_name || 'CitizenGraph_Thesis_Timeline_2026_2027.xlsx'
  const filePathDisplay = data?.file_path || `C:\\Users\\Acer\\OneDrive\\Documents\\4RTH-YEAR THESIS RESARCH AND DOCUMENTATION\\${fileName}`

  const p1 = dashboard?.phase_1 || { total: 12, completed: 4, in_progress: 1, pending: 7, completion_pct: 33.3, deadline: '2nd Week of Dec 2026' }
  const p2 = dashboard?.phase_2 || { total: 9, completed: 0, in_progress: 0, pending: 9, completion_pct: 0, deadline: 'Feb 2027' }
  const rSummary = dashboard?.roadmap || {
    total: roadmap.length,
    completed: roadmap.filter((s) => s.status === 'Completed').length,
    in_progress: roadmap.filter((s) => s.status === 'In Progress').length,
    pending: roadmap.filter((s) => s.status === 'Pending').length,
    completion_pct: Math.round((roadmap.filter((s) => s.status === 'Completed').length / Math.max(1, roadmap.length)) * 100),
  }
  const wbsSummary = dashboard?.overall_wbs || {
    total: wbs.length || 21,
    completed: wbs.length ? wbs.filter((t) => t.status === 'Completed').length : 4,
    in_progress: wbs.length ? wbs.filter((t) => t.status === 'In Progress').length : 1,
    pending: wbs.length ? wbs.filter((t) => t.status === 'Pending').length : 16,
    completion_pct: wbs.length
      ? Math.round((wbs.filter((t) => t.status === 'Completed').length / wbs.length) * 100)
      : 19,
  }
  const targets = dashboard?.quantitative_targets || []

  // Handlers
  const handleOpenExcel = async () => {
    setBusyAction(true)
    setFeedback({ type: 'info', msg: 'Opening CitizenGraph timeline in Microsoft Excel...' })
    try {
      const res = await openTimelineInExcel()
      setFeedback({ type: 'success', msg: res?.message || 'Opened timeline in Excel.' })
    } catch (err) {
      setFeedback({ type: 'error', msg: err.message || 'Failed to open Excel.' })
    } finally {
      setBusyAction(false)
    }
  }

  const handleSyncBaseline = async () => {
    setBusyAction(true)
    setFeedback({ type: 'info', msg: 'Committing current timeline state as new baseline...' })
    try {
      const res = await syncTimelineBaseline()
      setFeedback({ type: 'success', msg: res?.message || 'Baseline committed successfully.' })
      if (onRefresh) onRefresh()
    } catch (err) {
      setFeedback({ type: 'error', msg: err.message || 'Failed to sync baseline.' })
    } finally {
      setBusyAction(false)
    }
  }

  const cleanSearch = searchQuery.trim().toLowerCase()

  // Filtered Roadmap (supports Phase 1, Phase 2, Completed, In Progress, Pending + search)
  const filteredRoadmap = roadmap.filter((s) => {
    if (roadmapFilter === 'COMPLETED' && s.status !== 'Completed') return false
    if (roadmapFilter === 'IN PROGRESS' && s.status !== 'In Progress') return false
    if (roadmapFilter === 'PENDING' && s.status !== 'Pending') return false
    if (roadmapFilter === 'PHASE 1' && !(s.phase || '').toLowerCase().includes('phase 1')) return false
    if (roadmapFilter === 'PHASE 2' && !(s.phase || '').toLowerCase().includes('phase 2')) return false
    if (cleanSearch) {
      const hay = `${s.stage_id} ${s.title} ${s.activities} ${s.milestone} ${s.calendar_span}`.toLowerCase()
      if (!hay.includes(cleanSearch)) return false
    }
    return true
  })

  // Filtered WBS
  const filteredWbs = wbs.filter((t) => {
    const matchPhase =
      wbsPhaseFilter === 'ALL'
        ? true
        : wbsPhaseFilter === 'PHASE 1'
        ? t.wbs_id.startsWith('1.')
        : t.wbs_id.startsWith('2.')
    const matchStatus =
      wbsStatusFilter === 'ALL' ? true : t.status.toUpperCase() === wbsStatusFilter
    const matchQuery = cleanSearch
      ? `${t.wbs_id} ${t.task_description} ${t.deliverable} ${t.module}`.toLowerCase().includes(cleanSearch)
      : true
    return matchPhase && matchStatus && matchQuery
  })

  // Active / Next Up Stage Spotlight for Right Sidebar
  const nextUpStage =
    roadmap.find((s) => s.stage_id === selectedStageId) ||
    roadmap.find((s) => s.status === 'In Progress') ||
    roadmap.find((s) => s.status === 'Pending') ||
    roadmap[0]

  // Priority Tasks for Right Sidebar (derived from live WBS / measurable tasks or fallback)
  const sidebarPriorityTasks = (
    wbs.length > 0
      ? wbs
          .filter((t) => t.status !== 'Completed')
          .map((t, i) => ({
            id: t.wbs_id,
            title: t.task_description,
            date: t.period || t.active_span || 'Scheduled',
            priority: i < 2 || t.status === 'In Progress' ? 'High' : 'Medium',
            phase: t.wbs_id.startsWith('1.') ? 'Phase 1' : 'Phase 2',
            status: t.status,
          }))
      : FALLBACK_PRIORITY_TASKS
  )
    .filter((pt) => {
      if (roadmapFilter === 'PHASE 1' && pt.phase !== 'Phase 1') return false
      if (roadmapFilter === 'PHASE 2' && pt.phase !== 'Phase 2') return false
      if (roadmapFilter === 'COMPLETED' && pt.status !== 'Completed') return false
      if (roadmapFilter === 'IN PROGRESS' && pt.status !== 'In Progress') return false
      if (roadmapFilter === 'PENDING' && pt.status !== 'Pending') return false
      if (cleanSearch && !`${pt.title} ${pt.date}`.toLowerCase().includes(cleanSearch)) return false
      return true
    })
    .slice(0, 4)

  const handleUnifiedFilter = (f) => {
    setRoadmapFilter(f)
    if (f === 'PHASE 1' || f === 'PHASE 2' || f === 'ALL') {
      setWbsPhaseFilter(f)
      if (f === 'ALL') setWbsStatusFilter('ALL')
    } else if (f === 'COMPLETED' || f === 'IN PROGRESS' || f === 'PENDING') {
      setWbsStatusFilter(f)
    }
  }

  const pendingEmails = priorityEmails.filter(
    (e) => (e.status || 'Pending').toLowerCase() === 'pending'
  )
  const pendingCount = pendingEmails.length

  // Filtered Priority Emails
  const filteredEmails = priorityEmails.filter((e) => {
    const meta = getEmailDomainMeta(e.sender)
    const matchDomain =
      emailDomainFilter === 'ALL'
        ? true
        : emailDomainFilter === 'PEOPLE'
        ? meta.isPerson
        : meta.brand.toUpperCase().includes(emailDomainFilter.toUpperCase())
    const isPending = (e.status || 'Pending').toLowerCase() === 'pending'
    const matchStatus =
      emailStatusFilter === 'ALL'
        ? true
        : emailStatusFilter === 'PENDING'
        ? isPending
        : !isPending
    return matchDomain && matchStatus
  })

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-4 lg:p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <section
        ref={panelRef}
        className="relative flex flex-col w-[96vw] max-w-[1520px] h-[92vh] rounded-2xl border border-scar/60 bg-[#090305]/98 text-bone shadow-[0_0_60px_rgba(220,38,38,0.3)] overflow-hidden font-sans"
      >
        {/* PROACTIVE EMAIL TOAST NOTIFICATION CONTAINER */}
        {toasts.length > 0 && (
          <div className="absolute top-16 right-6 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
            {toasts.map((toast) => (
              <aside
                key={toast.id}
                role="status"
                aria-live="polite"
                className="pointer-events-auto flex items-start gap-3 p-3.5 rounded-xl border border-amber-400/90 bg-[#160408]/98 backdrop-blur-md text-bone shadow-[0_0_30px_rgba(245,158,11,0.35)] animate-fadeIn transition"
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
                  onClick={() => dismissToast(toast.id)}
                  className="text-ash hover:text-white text-xs px-1 hover:bg-scar/30 rounded"
                  title="Dismiss notification"
                >
                  ✕
                </button>
              </aside>
            ))}
          </div>
        )}

        {/* TOP COMMAND HEADER BAR (Neon Nightmare Thesis Timeline Dashboard.png) */}
        <header className="flex flex-wrap items-center justify-between border-b border-[#dc143c]/35 px-5 py-3 bg-gradient-to-r from-[#140307] via-[#0c0205] to-[#140307] shrink-0 gap-3">
          <div className="flex items-center gap-3.5 min-w-0">
            <Level5EyeLogo mode="idle" size={38} />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="text-base sm:text-lg font-extrabold tracking-[0.14em] text-white font-display uppercase">
                  CITIZEN GRAPH / THESIS TIMELINE
                </h1>
                <span className="rounded-full bg-[#ff2a4b]/25 border border-[#ff2a4b]/60 px-2.5 py-0.5 text-[10px] font-mono font-bold text-[#ffd166] uppercase tracking-widest">
                  L5 ARCHITECT
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-2.5 text-[11px] font-mono text-ash mt-0.5">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
                  Local File Connected
                </span>
                <span className="text-ash/40">|</span>
                <span className="truncate max-w-[260px] text-bone/85" title={filePathDisplay}>
                  {filePathDisplay}
                </span>
                <span className="text-ash/40">|</span>
                <span className="text-bone/85">Aug 2026 – Mar 2027</span>
                <span className="text-ash/40">|</span>
                <span className="text-bone/85">8 Months</span>
              </div>
            </div>
          </div>

          {/* Search Bar + Voice Pill + Action Buttons */}
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            {feedback && (
              <span
                className={`text-[11px] font-mono px-2.5 py-1 rounded border animate-fadeIn ${
                  feedback.type === 'success'
                    ? 'border-emerald-500/50 bg-emerald-950/40 text-emerald-300'
                    : feedback.type === 'error'
                    ? 'border-crimson/60 bg-crimson/20 text-rose-300'
                    : 'border-gold/40 bg-gold/10 text-gold'
                }`}
              >
                {feedback.msg}
              </span>
            )}

            {/* Search Input matching Neon Nightmare Thesis Timeline Dashboard.png */}
            <div className="flex items-center gap-2 rounded-full border border-[#ff2a4b]/45 bg-[#120307]/90 px-3 py-1.5 text-xs">
              <Icon name="search" size={13} className="text-[#ff5466]" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search timeline, tasks, or files..."
                className="w-44 sm:w-56 bg-transparent text-xs text-white placeholder-ash/70 focus:outline-none"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="text-[10px] text-ash hover:text-white"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Voice Command Pill */}
            <div className="hidden xl:flex items-center gap-2 rounded-full border border-[#ff2a4b]/65 bg-[#190409]/90 px-3 py-1.5 text-xs text-bone shadow-[0_0_16px_rgba(255,42,75,0.2)]">
              <span className="text-[#ff2a4b] font-bold">•••</span>
              <span className="text-ash">You asked:</span>
              <span className="font-mono font-semibold text-white">/timeline</span>
              <Icon name="mic" size={13} className="text-[#ff2a4b]" />
            </div>

            <a
              href={gdriveUrl}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-lg border border-scar/50 bg-abyss/80 px-2.5 py-1.5 text-[11px] font-mono font-bold text-sky-300 transition hover:border-sky-400/80 hover:text-white"
              title="Open CitizenGraph Master Timeline in Google Sheets"
            >
              <Icon name="external" className="h-3.5 w-3.5 text-sky-400" />
              <span className="hidden sm:inline">GDRIVE</span>
            </a>

            <button
              type="button"
              disabled={busyAction}
              onClick={handleOpenExcel}
              className="flex items-center gap-1.5 rounded-lg border border-scar/50 bg-abyss/80 px-2.5 py-1.5 text-[11px] font-mono font-bold text-ash transition hover:border-emerald-400/80 hover:text-white"
              title="Open master workbook in Microsoft Excel"
            >
              <Icon name="external" className="h-3.5 w-3.5 text-emerald-400" />
              <span className="hidden sm:inline">EXCEL</span>
            </button>

            <button
              type="button"
              disabled={busyAction}
              onClick={handleSyncBaseline}
              className="flex items-center gap-1.5 rounded-lg border border-scar/50 bg-abyss/80 px-2.5 py-1.5 text-[11px] font-mono font-bold text-gold transition hover:border-gold"
              title="Sync Baseline"
            >
              <Icon name="check" className="h-3.5 w-3.5 text-gold" />
              <span className="hidden sm:inline">SYNC</span>
            </button>

            <button
              type="button"
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-lg border border-scar/50 bg-abyss/80 text-ash transition hover:border-[#ff2a4b] hover:text-white"
              title="Close Timeline Dashboard"
            >
              <Icon name="x" className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* SUB-NAVIGATION TABS + UNIFIED PHASE/STATUS FILTERS BAR */}
        <nav
          className="flex flex-wrap items-center justify-between gap-2 px-5 py-2 border-b border-[#dc143c]/25 bg-[#0c0205] shrink-0"
          role="tablist"
        >
          {/* Left View Switchers */}
          <div className="flex items-center gap-1.5 overflow-x-auto">
            {[
              { id: 'summary', label: 'Overview' },
              { id: 'roadmap', label: 'Roadmap', badge: roadmap.length },
              { id: 'wbs', label: 'Weekly Tasks', badge: wbs.length || 21 },
              { id: 'objectives', label: 'Objectives & KPIs', badge: objectives.length || null },
              {
                id: 'diff',
                label: 'GDrive Diff',
                badge: diff.has_changes ? `${diff.change_count} NEW` : null,
                pulse: diff.has_changes,
              },
              {
                id: 'emails',
                label: 'Priority Inbox',
                badge: priorityEmails.length > 0 ? `${priorityEmails.length}` : null,
                pulse: pendingCount > 0,
              },
              {
                id: 'calendar_tasks',
                label: 'Calendar & Tasks',
                badge: calendarEvents.length + measurableTasks.length > 0 ? `${calendarEvents.length + measurableTasks.length}` : null,
              },
            ].map((tab) => {
              const active = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveTab(tab.id)}
                  className={`relative flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-xs font-semibold transition ${
                    active
                      ? 'border border-[#ff2a4b] bg-gradient-to-r from-[#ff2a4b]/35 to-[#ff2a4b]/10 text-white shadow-[0_0_18px_rgba(255,42,75,0.3)]'
                      : 'border border-scar/40 bg-[#140307]/70 text-ash hover:text-white hover:border-[#ff2a4b]/50'
                  }`}
                >
                  <span>{tab.label}</span>
                  {tab.badge && (
                    <span
                      className={`rounded-full px-1.5 py-0.2 text-[10px] font-mono font-bold ${
                        tab.pulse
                          ? 'bg-amber-500 text-black animate-pulse'
                          : active
                          ? 'bg-[#ff2a4b]/60 text-white'
                          : 'bg-scar/40 text-ash'
                      }`}
                    >
                      {tab.badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Right Unified Phase & Status Filters (matching Neon Nightmare Thesis Timeline Dashboard.png) */}
          <div className="flex flex-wrap items-center gap-1.5">
            <div className="flex items-center rounded-xl border border-scar/50 bg-[#120307] p-0.5">
              {[
                { key: 'ALL', label: 'All' },
                { key: 'PHASE 1', label: 'Phase 1' },
                { key: 'PHASE 2', label: 'Phase 2' },
              ].map((f) => {
                const active = roadmapFilter === f.key
                return (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => handleUnifiedFilter(f.key)}
                    className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
                      active
                        ? 'bg-[#ff2a4b] text-white shadow-[0_0_12px_rgba(255,42,75,0.5)]'
                        : 'text-ash hover:text-white'
                    }`}
                  >
                    {f.label}
                  </button>
                )
              })}
            </div>

            <div className="flex items-center rounded-xl border border-scar/50 bg-[#120307] p-0.5">
              {[
                { key: 'COMPLETED', label: 'Completed' },
                { key: 'IN PROGRESS', label: 'In Progress' },
                { key: 'PENDING', label: 'Pending' },
              ].map((f) => {
                const active = roadmapFilter === f.key
                return (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => handleUnifiedFilter(active ? 'ALL' : f.key)}
                    className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
                      active
                        ? 'bg-[#ff2a4b] text-white shadow-[0_0_12px_rgba(255,42,75,0.5)]'
                        : 'text-ash hover:text-white'
                    }`}
                  >
                    {f.label}
                  </button>
                )
              })}
            </div>
          </div>
        </nav>

        {/* MAIN BODY */}
        <div ref={contentRef} className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5">
          {/* ================================================================ */}
          {/* TAB 1: NEON NIGHTMARE THESIS TIMELINE OVERVIEW                  */}
          {/* ================================================================ */}
          {activeTab === 'summary' && (
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4 items-start">
              {/* LEFT / MAIN TIMELINE COLUMN */}
              <div className="min-w-0 space-y-4">
                {/* 1. OVERVIEW KPI ROW (4 Cards at a glance) */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {/* Overall Progress Radial Card */}
                  <div className="l5-card rounded-2xl p-3.5 flex items-center gap-3.5">
                    <div className="relative flex h-16 w-16 shrink-0 items-center justify-center">
                      <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
                        <circle
                          cx="32"
                          cy="32"
                          r="26"
                          fill="none"
                          stroke="rgba(255,42,75,0.18)"
                          strokeWidth="5"
                        />
                        <circle
                          cx="32"
                          cy="32"
                          r="26"
                          fill="none"
                          stroke="#ff2a4b"
                          strokeWidth="5"
                          strokeLinecap="round"
                          strokeDasharray={`${(Math.min(100, Math.max(0, wbsSummary.completion_pct)) / 100) * 163.36} 163.36`}
                          style={{ filter: 'drop-shadow(0 0 6px #ff2a4b)' }}
                        />
                      </svg>
                      <span className="absolute font-mono text-sm font-extrabold text-white">
                        {Math.round(wbsSummary.completion_pct)}%
                      </span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-extrabold uppercase tracking-wider text-white">
                        OVERALL PROGRESS
                      </div>
                      <div className="text-[11px] text-ash truncate">
                        Thesis completion (detailed tasks)
                      </div>
                      <div className="mt-2 flex items-center gap-2">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/10">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-[#dc143c] to-[#ff2a4b] shadow-[0_0_8px_#ff2a4b]"
                            style={{ width: `${Math.min(100, Math.max(0, wbsSummary.completion_pct))}%` }}
                          />
                        </div>
                        <span className="font-mono text-[11px] font-bold text-white">
                          {Math.round(wbsSummary.completion_pct)}%
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Completed Card */}
                  <div
                    onClick={() => handleUnifiedFilter(roadmapFilter === 'COMPLETED' ? 'ALL' : 'COMPLETED')}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && handleUnifiedFilter('COMPLETED')}
                    className="l5-card cursor-pointer rounded-2xl p-3.5 flex items-center gap-3.5"
                  >
                    <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full border-2 border-emerald-400 bg-emerald-500/15 text-emerald-400 shadow-[0_0_16px_rgba(16,185,129,0.35)]">
                      <Icon name="check" size={22} />
                    </div>
                    <div>
                      <div className="text-2xl font-extrabold leading-none text-white">
                        {wbsSummary.completed}
                      </div>
                      <div className="mt-1 text-[11px] font-bold uppercase tracking-wider text-emerald-400">
                        COMPLETED
                      </div>
                      <div className="text-[11px] text-ash">Work packages done</div>
                    </div>
                  </div>

                  {/* In Progress Card */}
                  <div
                    onClick={() => handleUnifiedFilter(roadmapFilter === 'IN PROGRESS' ? 'ALL' : 'IN PROGRESS')}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && handleUnifiedFilter('IN PROGRESS')}
                    className="l5-card cursor-pointer rounded-2xl p-3.5 flex items-center gap-3.5"
                  >
                    <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full border-2 border-amber-400 bg-amber-500/15 text-amber-400 shadow-[0_0_16px_rgba(251,191,36,0.35)]">
                      <span className="h-3 w-3 rounded-full bg-amber-400 animate-ping" />
                    </div>
                    <div>
                      <div className="text-2xl font-extrabold leading-none text-white">
                        {wbsSummary.in_progress}
                      </div>
                      <div className="mt-1 text-[11px] font-bold uppercase tracking-wider text-amber-400">
                        IN PROGRESS
                      </div>
                      <div className="text-[11px] text-ash">Currently active</div>
                    </div>
                  </div>

                  {/* Pending Card */}
                  <div
                    onClick={() => handleUnifiedFilter(roadmapFilter === 'PENDING' ? 'ALL' : 'PENDING')}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && handleUnifiedFilter('PENDING')}
                    className="l5-card cursor-pointer rounded-2xl p-3.5 flex items-center gap-3.5"
                  >
                    <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full border-2 border-[#ff2a4b] bg-[#ff2a4b]/15 text-[#ff2a4b] shadow-[0_0_16px_rgba(255,42,75,0.35)]">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                        <circle cx="12" cy="12" r="9" />
                        <path d="M12 7v5l3 2" />
                      </svg>
                    </div>
                    <div>
                      <div className="text-2xl font-extrabold leading-none text-white">
                        {wbsSummary.pending}
                      </div>
                      <div className="mt-1 text-[11px] font-bold uppercase tracking-wider text-[#ff5466]">
                        PENDING
                      </div>
                      <div className="text-[11px] text-ash">Yet to be started</div>
                    </div>
                  </div>
                </div>

                {/* 2. 8-MONTH HORIZONTAL ROADMAP (Aug 2026 – Mar 2027) */}
                <div className="l5-card rounded-2xl p-4 relative overflow-hidden">
                  <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                    <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-white">
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#ff2a4b" strokeWidth="2">
                        <rect x="3" y="4" width="18" height="17" rx="2" />
                        <path d="M16 2v4M8 2v4M3 10h18" />
                      </svg>
                      <span>8-MONTH ROADMAP</span>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-ash">Current Stage</span>
                      <span className="rounded-lg border border-amber-500/60 bg-amber-500/15 px-2.5 py-0.5 font-mono text-[10.5px] font-bold text-amber-300">
                        PHASE 1 • AUG 2026 – DEC 2026
                      </span>
                      <span className="flex items-center gap-1 font-mono text-[11px] font-bold text-[#ff5466]">
                        <span>∨</span>
                        <span>Today</span>
                      </span>
                    </div>
                  </div>

                  {/* 8 Month Columns Header + Phase Boundaries + Node Track */}
                  <div className="relative pt-1 pb-2 overflow-x-auto">
                    <div className="min-w-[760px] relative">
                      {/* Vertical "Today" Marker Line */}
                      <div
                        aria-hidden
                        className="pointer-events-none absolute top-0 bottom-0 z-10 w-[1.5px] bg-gradient-to-b from-[#ff2a4b] via-[#ff2a4b]/80 to-transparent shadow-[0_0_10px_#ff2a4b]"
                        style={{ left: '53%' }}
                      />

                      {/* Month Labels Grid */}
                      <div className="grid grid-cols-8 text-center font-mono text-[11px] font-semibold text-ash border-b border-white/10 pb-2">
                        {['AUG 2026', 'SEP 2026', 'OCT 2026', 'NOV 2026', 'DEC 2026', 'JAN 2027', 'FEB 2027', 'MAR 2027'].map((m) => (
                          <div key={m} className="border-r border-white/5 last:border-r-0">
                            {m}
                          </div>
                        ))}
                      </div>

                      {/* Phase 1 & Phase 2 Boundary Bars */}
                      <div className="mt-3 grid grid-cols-8 gap-2">
                        <div className="col-span-5 rounded-lg border border-[#ff2a4b]/60 bg-gradient-to-r from-[#ff2a4b]/30 via-[#ff2a4b]/20 to-[#ff2a4b]/10 px-3 py-1.5 text-center text-xs font-bold text-white shadow-[0_0_15px_rgba(255,42,75,0.2)]">
                          <span className="text-[#ff5466] mr-2">PHASE 1</span>
                          <span className="font-normal text-bone/90">Aug 2026 – Dec 2026</span>
                        </div>
                        <div className="col-span-3 rounded-lg border border-amber-500/60 bg-gradient-to-r from-amber-500/25 via-amber-500/15 to-amber-500/10 px-3 py-1.5 text-center text-xs font-bold text-amber-200 shadow-[0_0_15px_rgba(245,158,11,0.15)]">
                          <span className="text-amber-400 mr-2">PHASE 2</span>
                          <span className="font-normal text-bone/90">Jan 2027 – Mar 2027</span>
                        </div>
                      </div>

                      {/* Connected Stage Node Line Track */}
                      <div className="relative mt-7 mb-2 px-4">
                        {/* Connecting horizontal line */}
                        <div className="absolute left-8 right-8 top-3.5 h-[2px] bg-gradient-to-r from-emerald-400 via-amber-400 to-sky-400/50" />

                        <div className="relative z-10 flex items-start justify-between gap-2 overflow-x-auto pb-1">
                          {roadmap.map((stg, idx) => {
                            const isDone = stg.status === 'Completed'
                            const isProg = stg.status === 'In Progress'
                            const selected = selectedStageId === stg.stage_id
                            return (
                              <button
                                key={stg.stage_id}
                                type="button"
                                onClick={() => setSelectedStageId(stg.stage_id)}
                                className={`group flex flex-col items-center text-center transition ${
                                  selected ? 'scale-105' : 'hover:scale-105'
                                }`}
                              >
                                <div
                                  className={`grid h-7 w-7 place-items-center rounded-full border-2 bg-[#0d0205] transition ${
                                    isDone
                                      ? 'border-emerald-400 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.6)]'
                                      : isProg
                                        ? 'border-amber-400 text-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.6)]'
                                        : 'border-sky-400/70 text-sky-300 shadow-[0_0_10px_rgba(56,189,248,0.35)]'
                                  }`}
                                >
                                  {isDone ? (
                                    <Icon name="check" size={14} />
                                  ) : (
                                    <span
                                      className={`h-2 w-2 rounded-full ${
                                        isProg ? 'bg-amber-400' : 'bg-sky-400'
                                      }`}
                                    />
                                  )}
                                </div>
                                <span
                                  className={`mt-2 font-mono text-[11px] font-bold ${
                                    isDone
                                      ? 'text-emerald-400'
                                      : isProg
                                        ? 'text-amber-300'
                                        : 'text-sky-300'
                                  }`}
                                >
                                  {stg.stage_id}
                                </span>
                                <span className="max-w-[105px] truncate text-[11px] text-bone/90">
                                  {stg.short_label || stg.title}
                                </span>
                                {idx === 3 && (
                                  <span className="mt-0.5 rounded bg-[#ff2a4b]/25 px-1.5 py-0.2 text-[9.5px] font-semibold text-[#ff5466]">
                                    Ch 1–3 Due (2nd wk)
                                  </span>
                                )}
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 3. MILESTONE ROADMAP CARDS ROW */}
                <div className="l5-card rounded-2xl p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-white">
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#ff2a4b" strokeWidth="2">
                        <rect x="3" y="4" width="18" height="17" rx="2" />
                        <path d="M16 2v4M8 2v4M3 10h18" />
                      </svg>
                      <span>MILESTONE ROADMAP</span>
                    </div>
                    <span className="font-mono text-[11px] text-ash">
                      Showing {filteredRoadmap.length} of {roadmap.length} Stages
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-3">
                    {filteredRoadmap.map((stg) => {
                      const isDone = stg.status === 'Completed'
                      const isProg = stg.status === 'In Progress'
                      const isSelected = selectedStageId === stg.stage_id
                      const borderClass = isDone
                        ? 'border-emerald-500/60 bg-gradient-to-b from-emerald-950/35 to-[#0c0306]'
                        : isProg
                          ? 'border-amber-500/60 bg-gradient-to-b from-amber-950/30 to-[#0c0306]'
                          : 'border-sky-500/35 bg-gradient-to-b from-slate-900/40 to-[#0c0306]'

                      return (
                        <article
                          key={stg.stage_id}
                          onClick={() => setSelectedStageId(stg.stage_id)}
                          className={`cursor-pointer rounded-2xl border p-3.5 flex flex-col justify-between transition ${borderClass} ${
                            isSelected ? 'ring-2 ring-[#ffd166]' : 'hover:border-white/40'
                          }`}
                        >
                          <div>
                            {/* Top Badges */}
                            <div className="flex items-center justify-between gap-2">
                              <span
                                className={`rounded-md px-2 py-0.5 font-mono text-[11px] font-bold ${
                                  isDone
                                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                    : isProg
                                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                      : 'bg-sky-500/20 text-sky-300 border border-sky-500/40'
                                }`}
                              >
                                {stg.stage_id}
                              </span>
                              <span
                                className={`rounded-full px-2 py-0.5 font-mono text-[9.5px] font-bold uppercase ${
                                  isDone
                                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                                    : isProg
                                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                      : 'bg-sky-500/15 text-sky-300 border border-sky-500/30'
                                }`}
                              >
                                {isDone ? 'COMPLETED' : isProg ? 'IN PROGRESS' : 'UPCOMING'}
                              </span>
                            </div>

                            {/* Stage Title */}
                            <h3 className="mt-2.5 text-sm font-bold leading-snug text-white">
                              {stg.title}
                            </h3>

                            {/* Dates */}
                            <p className="mt-1.5 font-mono text-[11px] text-ash">
                              📅 {stg.calendar_span || stg.stage_name}
                            </p>

                            {/* Description */}
                            <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-bone/85">
                              {stg.activities || 'Milestone execution and validation.'}
                            </p>
                          </div>

                          {/* Next Deliverable Footer + Progress Bar */}
                          <div className="mt-3.5 border-t border-white/10 pt-2.5">
                            <div className="text-[10.5px] font-semibold text-ash flex items-center gap-1.5">
                              <span className={isDone ? 'text-emerald-400' : isProg ? 'text-amber-400' : 'text-sky-400'}>
                                {isDone ? '✓' : '★'}
                              </span>
                              <span>Next Deliverable</span>
                            </div>
                            <div className="mt-0.5 truncate text-xs font-bold text-white" title={stg.milestone}>
                              {stg.milestone || 'Approved Stage Output'}
                            </div>

                            <div className="mt-2 flex items-center gap-2">
                              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                                <div
                                  className={`h-full rounded-full ${
                                    isDone
                                      ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]'
                                      : isProg
                                        ? 'bg-amber-400 shadow-[0_0_8px_#fbbf24]'
                                        : 'bg-sky-400'
                                  }`}
                                  style={{ width: `${stg.progress_pct}%` }}
                                />
                              </div>
                              <span className="font-mono text-[10.5px] text-ash">{stg.progress_pct}%</span>
                            </div>
                          </div>
                        </article>
                      )
                    })}
                  </div>
                </div>
              </div>

              {/* RIGHT SIDEBAR (NEXT UP + PRIORITY TASKS + ROADMAP DEPENDENCIES) */}
              <aside className="space-y-3.5">
                {/* 1. NEXT UP Spotlight Card */}
                {nextUpStage && (
                  <div className="l5-card rounded-2xl p-4">
                    <div className="flex items-center justify-between mb-2.5">
                      <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-white">
                        <Icon name="gauge" size={15} className="text-[#ff2a4b]" />
                        <span>NEXT UP</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setActiveTab('roadmap')}
                        className="text-[11px] font-medium text-[#ff5466] hover:text-white transition"
                      >
                        View All →
                      </button>
                    </div>

                    <div className="rounded-xl border border-amber-500/40 bg-[#140408]/90 p-3">
                      <div className="flex items-center justify-between gap-2">
                        <span className="rounded bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 font-mono text-[11px] font-bold text-amber-300">
                          {nextUpStage.stage_id}
                        </span>
                        <span className="rounded-full bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 font-mono text-[9.5px] font-bold uppercase text-amber-300">
                          {nextUpStage.status}
                        </span>
                      </div>
                      <h4 className="mt-2 text-sm font-bold text-white leading-snug">
                        {nextUpStage.title}
                      </h4>
                      <p className="mt-1 font-mono text-[11px] text-ash">
                        📅 {nextUpStage.calendar_span || nextUpStage.stage_name}
                      </p>
                      <p className="mt-2 text-xs text-bone/85 leading-relaxed">
                        {nextUpStage.activities}
                      </p>
                      <button
                        type="button"
                        onClick={() => setActiveTab('wbs')}
                        className="mt-3 w-full rounded-lg border border-[#ff2a4b]/60 bg-[#ff2a4b]/20 py-1.5 text-xs font-semibold text-white hover:bg-[#ff2a4b]/35 transition"
                      >
                        View Details →
                      </button>
                    </div>
                  </div>
                )}

                {/* 2. PRIORITY TASKS Card */}
                <div className="l5-card rounded-2xl p-4">
                  <div className="flex items-center justify-between mb-2.5">
                    <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-white">
                      <Icon name="bolt" size={15} className="text-[#ff2a4b]" />
                      <span>PRIORITY TASKS</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setActiveTab('wbs')}
                      className="text-[11px] font-medium text-[#ff5466] hover:text-white transition"
                    >
                      WBS →
                    </button>
                  </div>

                  <div className="divide-y divide-[#ff2a4b]/15">
                    {sidebarPriorityTasks.map((pt) => (
                      <div key={pt.id} className="py-2 first:pt-0 last:pb-0 flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                            <span className="truncate text-xs font-semibold text-white" title={pt.title}>
                              {pt.title}
                            </span>
                          </div>
                          <div className="mt-0.5 pl-3 font-mono text-[10.5px] text-ash">
                            📅 {pt.date}
                          </div>
                        </div>
                        <span
                          className={`shrink-0 rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
                            pt.priority === 'High'
                              ? 'bg-[#ff2a4b]/25 text-[#ff5466] border border-[#ff2a4b]/50'
                              : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                          }`}
                        >
                          {pt.priority}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* 3. ROADMAP DEPENDENCIES Branching Node-Line Graph */}
                <div className="l5-card rounded-2xl p-4">
                  <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-wider text-white mb-2">
                    <Icon name="spark" size={15} className="text-[#ff2a4b]" />
                    <span>ROADMAP DEPENDENCIES</span>
                  </div>

                  <div className="relative h-52 w-full">
                    <svg viewBox="0 0 280 195" className="h-full w-full overflow-visible">
                      {/* Curved Branching Dependency Paths */}
                      <path
                        d="M 28 24 C 28 55, 65 55, 78 58"
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="1.6"
                        strokeOpacity="0.75"
                      />
                      <path
                        d="M 28 24 C 28 92, 65 92, 78 95"
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="1.6"
                        strokeOpacity="0.75"
                      />
                      <path
                        d="M 92 58 C 135 58, 155 76, 195 78"
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="1.6"
                        strokeOpacity="0.75"
                      />
                      <path
                        d="M 92 95 C 135 95, 155 82, 195 78"
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth="1.6"
                        strokeOpacity="0.75"
                      />
                      <path
                        d="M 195 78 C 195 110, 150 118, 148 132"
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth="1.6"
                        strokeOpacity="0.7"
                      />
                      <path
                        d="M 148 132 C 110 145, 75 155, 52 168"
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth="1.6"
                        strokeOpacity="0.7"
                      />
                      <path
                        d="M 148 132 C 165 150, 178 160, 185 170"
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth="1.6"
                        strokeOpacity="0.7"
                      />

                      {/* Dependency Graph Nodes (STG-01 .. STG-07) */}
                      {[
                        { id: 'STG-01', x: 28, y: 24, fallbackStatus: 'Completed' },
                        { id: 'STG-02', x: 85, y: 58, fallbackStatus: 'In Progress' },
                        { id: 'STG-03', x: 85, y: 95, fallbackStatus: 'In Progress' },
                        { id: 'STG-04', x: 195, y: 78, fallbackStatus: 'In Progress' },
                        { id: 'STG-05', x: 148, y: 132, fallbackStatus: 'Pending' },
                        { id: 'STG-06', x: 52, y: 168, fallbackStatus: 'Pending' },
                        { id: 'STG-07', x: 185, y: 170, fallbackStatus: 'Pending' },
                      ].map((node) => {
                        const liveStg = roadmap.find((s) => s.stage_id === node.id)
                        const st = liveStg?.status || node.fallbackStatus
                        const isDone = st === 'Completed'
                        const isProg = st === 'In Progress'
                        const stroke = isDone ? '#34d399' : isProg ? '#fbbf24' : '#38bdf8'
                        return (
                          <g
                            key={node.id}
                            onClick={() => setSelectedStageId(node.id)}
                            className="cursor-pointer"
                          >
                            <circle
                              cx={node.x}
                              cy={node.y}
                              r="9"
                              fill="#0b0204"
                              stroke={stroke}
                              strokeWidth="2.2"
                            />
                            <circle cx={node.x} cy={node.y} r="3.5" fill={stroke} />
                            <text
                              x={node.x + 14}
                              y={node.y - 1}
                              fill="#ffffff"
                              fontSize="10"
                              fontWeight="700"
                              fontFamily="monospace"
                            >
                              {node.id}
                            </text>
                            <text
                              x={node.x + 14}
                              y={node.y + 10}
                              fill={stroke}
                              fontSize="9"
                              fontFamily="sans-serif"
                            >
                              {isDone ? 'Completed' : isProg ? 'In Progress' : 'Upcoming'}
                            </text>
                          </g>
                        )
                      })}
                    </svg>
                  </div>
                </div>

                <p className="text-center text-xs italic text-[#ff5466]/90">
                  &ldquo;Better systems. Fewer barriers. More citizens.&rdquo;
                </p>
              </aside>
            </div>
          )}

          {/* ================================================================ */}
          {/* TAB 2: 8-MONTH ROADMAP (Sheet 1)                                */}
          {/* ================================================================ */}
          {activeTab === 'roadmap' && (
            <div className="space-y-4">
              {/* Filter Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-scar/30 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono uppercase text-ash">Filter Stages:</span>
                  {['ALL', 'COMPLETED', 'IN PROGRESS', 'PENDING', 'PHASE 1', 'PHASE 2'].map((f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setRoadmapFilter(f)}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-mono font-bold transition ${
                        roadmapFilter === f
                          ? 'bg-crimson/40 text-amber-300 border border-crimson/60 shadow-[0_0_10px_rgba(220,38,38,0.2)]'
                          : 'bg-scar/20 text-ash hover:text-white'
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
                <span className="text-xs font-mono text-ash">
                  Showing {filteredRoadmap.length} of {roadmap.length} Roadmap Stages
                </span>
              </div>

              {/* Roadmap Stage Cards */}
              <div className="space-y-3">
                {filteredRoadmap.map((stage) => (
                  <article
                    key={stage.stage_id}
                    className="rounded-xl border border-scar/40 bg-abyss/80 p-4 transition hover:border-scar/80 shadow-md flex flex-col xl:flex-row xl:items-center justify-between gap-4"
                  >
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <span className="rounded bg-crimson/30 border border-crimson/60 px-2 py-0.5 text-xs font-mono font-bold text-amber-300">
                          {stage.stage_id}
                        </span>
                        <span className="text-xs font-mono text-ash bg-scar/30 px-2 py-0.5 rounded">
                          {stage.stage_name}
                        </span>
                        <span className="text-xs font-mono text-sky-400 bg-sky-950/40 border border-sky-800/50 px-2 py-0.5 rounded">
                          {stage.calendar_span}
                        </span>
                        <span className="text-xs font-mono text-ash/80">
                          {stage.phase}
                        </span>
                        <StatusBadge status={stage.status} />
                      </div>

                      <h3 className="text-sm font-bold text-bone">
                        {stage.title}
                      </h3>
                      <p className="text-xs font-mono text-ash leading-relaxed">
                        <strong className="text-bone/90">Activities:</strong> {stage.activities}
                      </p>
                      {stage.milestone && (
                        <p className="text-xs font-mono text-amber-300/90 flex items-center gap-1.5">
                          <span>★</span>
                          <span><strong className="text-amber-400">Milestone:</strong> {stage.milestone}</span>
                        </p>
                      )}
                    </div>

                    {/* 8-Month Mini-Track */}
                    <div className="shrink-0 xl:w-72 bg-[#120508] border border-scar/30 rounded-lg p-2.5 space-y-1.5">
                      <span className="text-[10px] font-mono text-ash/80 uppercase tracking-wider block text-center">
                        Active 8-Month Track (Aug '26 - Mar '27)
                      </span>
                      <div className="grid grid-cols-8 gap-1">
                        {stage.months.map((m) => (
                          <div
                            key={m.month_index}
                            className={`h-7 rounded flex flex-col items-center justify-center text-[9px] font-mono transition-all ${
                              m.active
                                ? 'bg-[#0284c7] text-white font-bold shadow-[0_0_8px_rgba(2,132,199,0.5)]'
                                : 'bg-scar/25 text-ash/60'
                            }`}
                            title={`${m.label}: ${m.active ? 'Active Stage Period' : 'Inactive'}`}
                          >
                            <span>M{m.month_index}</span>
                            {m.active && <span className="text-[7px]">●</span>}
                          </div>
                        ))}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {/* ================================================================ */}
          {/* TAB 3: PHASE 1 & 2 WEEKLY WBS (Sheet 2)                          */}
          {/* ================================================================ */}
          {activeTab === 'wbs' && (
            <div className="space-y-4">
              {/* Dual Filter Controls */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-scar/30 pb-3">
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono uppercase text-ash">Phase:</span>
                    {['ALL', 'PHASE 1', 'PHASE 2'].map((pf) => (
                      <button
                        key={pf}
                        type="button"
                        onClick={() => setWbsPhaseFilter(pf)}
                        className={`rounded-md px-2.5 py-1 text-[11px] font-mono font-bold transition ${
                          wbsPhaseFilter === pf
                            ? 'bg-crimson/40 text-amber-300 border border-crimson/60'
                            : 'bg-scar/20 text-ash hover:text-white'
                        }`}
                      >
                        {pf === 'ALL' ? 'ALL (21)' : pf === 'PHASE 1' ? 'PHASE 1 (12)' : 'PHASE 2 (9)'}
                      </button>
                    ))}
                  </div>

                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono uppercase text-ash">Status:</span>
                    {['ALL', 'COMPLETED', 'IN PROGRESS', 'PENDING'].map((sf) => (
                      <button
                        key={sf}
                        type="button"
                        onClick={() => setWbsStatusFilter(sf)}
                        className={`rounded-md px-2.5 py-1 text-[11px] font-mono font-bold transition ${
                          wbsStatusFilter === sf
                            ? 'bg-crimson/40 text-amber-300 border border-crimson/60'
                            : 'bg-scar/20 text-ash hover:text-white'
                        }`}
                      >
                        {sf}
                      </button>
                    ))}
                  </div>
                </div>

                <span className="text-xs font-mono text-ash">
                  Showing {filteredWbs.length} of {wbs.length} WBS Tasks
                </span>
              </div>

              {/* High-Clarity Desktop Table */}
              <div className="rounded-xl border border-scar/40 bg-abyss/80 overflow-hidden shadow-lg">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-scar/40 bg-scar/20 text-[11px] font-mono uppercase text-ash tracking-wider">
                      <th className="py-3 px-4 w-20">WBS ID</th>
                      <th className="py-3 px-4 w-28">Phase</th>
                      <th className="py-3 px-4">Task & System Module</th>
                      <th className="py-3 px-4">Key Deliverable</th>
                      <th className="py-3 px-4 w-64">Period & Timeline Window</th>
                      <th className="py-3 px-4 w-36 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-scar/20 text-xs font-mono">
                    {filteredWbs.map((task) => (
                      <tr
                        key={task.wbs_id}
                        className="transition hover:bg-scar/15 group"
                      >
                        <td className="py-3 px-4 font-bold text-amber-300">
                          {task.wbs_id}
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                              task.wbs_id.startsWith('1.')
                                ? 'bg-sky-500/15 border border-sky-500/40 text-sky-300'
                                : 'bg-teal-500/15 border border-teal-500/40 text-teal-300'
                            }`}
                          >
                            {task.wbs_id.startsWith('1.') ? 'Phase 1' : 'Phase 2'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <p className="font-bold text-bone text-[12.5px] leading-snug">
                            {task.task_description}
                          </p>
                          {task.module && (
                            <p className="text-[11px] text-ash/80 mt-0.5 font-normal">
                              {task.module}
                            </p>
                          )}
                        </td>
                        <td className="py-3 px-4 text-bone/90 leading-snug">
                          {task.deliverable || '—'}
                        </td>
                        <td className="py-3 px-4">
                          <span className="rounded bg-[#1a080e] border border-scar/40 px-2.5 py-1 text-[11px] text-sky-300 font-bold block mb-1.5 w-fit">
                            {task.period || task.active_span}
                          </span>
                          {/* 6-Month Compressed Visual Track (Sept - Feb) */}
                          <div className="grid grid-cols-6 gap-1 w-44">
                            {['Sept', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb'].map((m) => {
                              const isActive = (task.active_months || []).includes(m)
                              return (
                                <div
                                  key={m}
                                  className={`h-2 rounded-xs ${
                                    isActive
                                      ? 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.6)]'
                                      : 'bg-scar/30'
                                  }`}
                                  title={`${m}: ${isActive ? 'Active' : 'Inactive'}`}
                                />
                              )
                            })}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <StatusBadge status={task.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ================================================================ */}
          {/* TAB 4: OBJECTIVES & KPIs (Sheet 3)                               */}
          {/* ================================================================ */}
          {activeTab === 'objectives' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-scar/30 pb-3">
                <h3 className="text-xs font-mono uppercase tracking-wider text-amber-400">
                  Chapter 1 Study Objectives (General + Specific) & Architectural Component Alignment
                </h3>
                <span className="text-xs font-mono text-ash">
                  Total: {objectives.length} Objectives
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3.5">
                {objectives.map((obj) => (
                  <article
                    key={obj.obj_id}
                    className="rounded-xl border border-scar/40 bg-abyss/80 p-4 transition hover:border-scar/80 shadow-md flex flex-col lg:flex-row lg:items-center justify-between gap-4"
                  >
                    <div className="min-w-0 flex-1 space-y-2">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <span className="rounded bg-crimson/30 border border-crimson/60 px-2.5 py-0.5 text-xs font-mono font-bold text-amber-300">
                          {obj.obj_id}
                        </span>
                        {obj.task_filter_type && (
                          <span className="rounded bg-indigo-950/50 border border-indigo-700/50 px-2 py-0.5 text-xs font-mono text-indigo-300">
                            {obj.task_filter_type}
                          </span>
                        )}
                        {obj.metric_category && (
                          <span className="rounded bg-emerald-950/40 border border-emerald-700/40 px-2 py-0.5 text-xs font-mono text-emerald-300">
                            {obj.metric_category}
                          </span>
                        )}
                        <span className="rounded bg-scar/30 px-2 py-0.5 text-xs font-mono text-ash">
                          {obj.primary_phase}
                        </span>
                        <span className="rounded bg-sky-950/40 border border-sky-800/40 px-2 py-0.5 text-xs font-mono text-sky-300">
                          Window: {obj.scheduled_window || 'TBD'}
                        </span>
                        <StatusBadge status={obj.status} />
                      </div>

                      <h3 className="text-sm font-bold text-bone leading-snug">
                        {obj.statement}
                      </h3>

                      {obj.team_goal && (
                        <p className="text-xs font-mono text-bone/80">
                          <strong className="text-amber-300/90">Team Goal / Action Plan:</strong>{' '}
                          {obj.team_goal}
                        </p>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs font-mono pt-1 text-ash">
                        <p>
                          <strong className="text-bone/90">Component:</strong>{' '}
                          <span className="text-amber-300/90">{obj.component}</span>
                        </p>
                        <p>
                          <strong className="text-bone/90">Dataset / Scope:</strong>{' '}
                          <span>{obj.dataset_scope}</span>
                        </p>
                      </div>
                    </div>

                    <div className="shrink-0 lg:w-72 bg-[#120508] border border-scar/30 rounded-lg p-3 space-y-1">
                      <span className="text-[10px] font-mono text-ash uppercase tracking-wider block">
                        Target Benchmark / KPI
                      </span>
                      <p className="text-xs font-mono font-bold text-amber-300">
                        {obj.target_kpi || 'Quantitative verification pending'}
                      </p>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {/* ================================================================ */}
          {/* TAB 5: GDRIVE DIFF & TEAM SYNC                                    */}
          {/* ================================================================ */}
          {activeTab === 'diff' && (
            <div className="space-y-6">
              {/* Google Drive Live Connection Card */}
              <div className="rounded-xl border border-sky-500/35 bg-[#0b101b]/90 p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-mono font-bold uppercase tracking-wider text-sky-300">
                      Google Sheets Master Workbook Sync
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-mono font-bold border ${
                        gdriveInfo.status === 'in_sync_with_gdrive'
                          ? 'border-emerald-500/60 bg-emerald-500/15 text-emerald-300'
                          : gdriveInfo.status === 'gdrive_changes_detected'
                            ? 'border-amber-400/80 bg-amber-500/20 text-amber-300'
                            : 'border-sky-500/40 bg-sky-500/15 text-sky-300'
                      }`}
                    >
                      {gdriveInfo.status === 'in_sync_with_gdrive'
                        ? 'GDRIVE IN SYNC'
                        : gdriveInfo.status === 'gdrive_changes_detected'
                          ? 'GDRIVE UPDATES DETECTED'
                          : (gdriveInfo.status || 'LOCAL + GDRIVE LINKED').toUpperCase()}
                    </span>
                  </div>
                  <p className="text-xs font-mono text-ash">
                    Local File: <span className="text-bone/90">{filePathDisplay}</span>
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <a
                    href={gdriveUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-lg border border-sky-400/60 bg-sky-500/15 px-3 py-1.5 text-xs font-mono font-bold text-sky-300 transition hover:bg-sky-500/25 hover:text-white"
                  >
                    Open Google Sheet ↗
                  </a>
                </div>
              </div>

              {/* Diff Telemetry & Actions Card */}
              <div className="rounded-xl border border-scar/50 bg-[#120509]/95 p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-mono font-bold uppercase tracking-wider text-amber-400">
                      Cross-Reference Diff Engine Telemetry
                    </h3>
                    <span
                      className={`text-[10.5px] font-mono font-bold px-2 py-0.5 rounded border ${
                        diff.has_changes
                          ? 'border-amber-400 bg-amber-500/20 text-amber-300 animate-pulse'
                          : 'border-emerald-500 bg-emerald-500/20 text-emerald-300'
                      }`}
                    >
                      {diff.has_changes ? `${diff.change_count} CHANGES DETECTED` : 'BASELINE IN SYNC'}
                    </span>
                  </div>
                  <p className="text-xs font-mono text-ash mt-1">
                    {diff.spoken_summary}
                  </p>
                </div>

                <div className="flex items-center gap-2.5">
                  <button
                    type="button"
                    disabled={busyAction}
                    onClick={handleSyncBaseline}
                    className="rounded-lg border border-amber-400/80 bg-amber-500/20 px-3.5 py-2 text-xs font-mono font-bold text-amber-300 transition hover:bg-amber-500/30 hover:border-amber-400 shadow-[0_0_15px_rgba(245,158,11,0.2)]"
                  >
                    Pull GDrive & Commit Baseline
                  </button>
                  {onRefresh && (
                    <button
                      type="button"
                      onClick={onRefresh}
                      className="rounded-lg border border-scar/40 bg-abyss/80 px-3 py-2 text-xs font-mono font-bold text-ash transition hover:border-white hover:text-white"
                    >
                      Re-Check Source
                    </button>
                  )}
                </div>
              </div>

              {/* Status Transitions & Schedule Shifts */}
              {diff.has_changes ? (
                <div className="space-y-4">
                  <h4 className="text-xs font-mono uppercase text-ash tracking-wider">
                    Categorized Diffs Against Baseline
                  </h4>

                  {diff.changes?.map((ch, idx) => (
                    <div
                      key={idx}
                      className="rounded-xl border border-scar/40 bg-abyss/80 p-4 flex flex-wrap items-center justify-between gap-4 shadow-sm"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-crimson/30 border border-crimson/60 px-2 py-0.5 text-xs font-mono font-bold text-amber-300">
                            {ch.item_key}
                          </span>
                          <span className="text-xs font-bold text-bone">
                            {ch.title}
                          </span>
                          <span className="text-[10px] font-mono text-ash uppercase bg-scar/30 px-2 py-0.5 rounded">
                            {ch.type.replace('_', ' ')}
                          </span>
                        </div>
                        <p className="text-xs font-mono text-ash mt-1">
                          {ch.detail}
                        </p>
                      </div>

                      {ch.type === 'status_transition' ? (
                        <div className="flex items-center gap-2 font-mono text-xs">
                          <StatusBadge status={ch.old_val} />
                          <span className="text-ash font-bold">→</span>
                          <StatusBadge status={ch.new_val} />
                        </div>
                      ) : (
                        <div className="text-right text-xs font-mono text-amber-300">
                          <span className="line-through text-ash mr-2">{ch.old_val}</span>
                          <span>{ch.new_val}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-scar/30 bg-abyss/60 p-8 text-center space-y-2">
                  <p className="text-sm font-mono font-bold text-emerald-400">
                    No discrepancies detected against baseline snapshot.
                  </p>
                  <p className="text-xs font-mono text-ash">
                    All {roadmap.length} roadmap stages, {wbs.length} WBS tasks, and {objectives.length} study objectives match the stored state.
                  </p>
                </div>
              )}

              {/* Team Quota Tracker & Stale Tasks with Level 5 Controls */}
              {quotas.length > 0 && (
                <div className="space-y-4 border-t border-scar/30 pt-6">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-amber-400">
                        Team Quotas & 3-Day Stale Email Nudgers
                      </h4>
                      <p className="text-[11px] font-mono text-ash mt-0.5">
                        Nightmare tracks tasks with no updates for &gt;= 3 days. Level 5 confirmation required to send SMTP nudges.
                      </p>
                    </div>
                    {staleTasks.length > 0 && (
                      <span className="rounded bg-crimson/40 border border-crimson/60 px-2.5 py-0.5 text-[11px] font-mono font-bold text-rose-300">
                        {staleTasks.length} Stale Action Required
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {quotas.map((q) => {
                      const isStale = Boolean(q.stale)
                      const isSnoozed = Boolean(q.snoozed)
                      const pct = Math.min(100, Math.max(0, q.progress_pct || 0))

                      return (
                        <div
                          key={q.task_id}
                          className={`rounded-xl border p-4 flex flex-col justify-between space-y-3 ${
                            isStale && !isSnoozed
                              ? 'border-crimson/80 bg-crimson/15 shadow-[0_0_20px_rgba(220,38,38,0.2)]'
                              : 'border-scar/40 bg-abyss/75'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-xs font-bold text-amber-300">
                                  {q.task_id}
                                </span>
                                <span className="rounded bg-scar/30 px-2 py-0.5 text-[10px] font-mono text-ash">
                                  {q.assigned_team}
                                </span>
                              </div>
                              <h5 className="text-xs font-bold text-bone mt-1">
                                {q.task_name}
                              </h5>
                              <p className="text-[11px] font-mono text-ash truncate">
                                Owner: {q.owner_email || 'No email registered'}
                              </p>
                            </div>
                            {isStale && !isSnoozed && (
                              <span className="rounded-full bg-crimson/40 border border-crimson/60 px-2 py-0.5 text-[10px] font-mono font-bold text-rose-300 animate-pulse">
                                STALE ({q.days_since_update}d)
                              </span>
                            )}
                          </div>

                          <div>
                            <div className="flex items-center justify-between text-[11px] font-mono text-ash mb-1">
                              <span>
                                {q.current_count} / {q.target_count} ({pct}%)
                              </span>
                            </div>
                            <div className="h-2 rounded-full bg-scar/40 overflow-hidden">
                              <div
                                className={`h-full transition-all duration-500 ${
                                  pct >= 100
                                    ? 'bg-emerald-400'
                                    : isStale
                                    ? 'bg-crimson'
                                    : 'bg-amber-400'
                                }`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>

                          {pendingAction && (
                            <div className="flex items-center gap-2 border-t border-scar/30 pt-2.5">
                              <button
                                type="button"
                                onClick={() => onApprove(pendingAction.id)}
                                className="flex-1 rounded border border-emerald-500/70 bg-emerald-500/20 py-1 text-xs font-mono font-bold text-emerald-300 hover:bg-emerald-500/30"
                              >
                                Approve Email Nudge
                              </button>
                              <button
                                type="button"
                                onClick={() => onDecline(pendingAction.id)}
                                className="rounded border border-scar/40 bg-scar/20 px-3 py-1 text-xs font-mono text-ash hover:text-white"
                              >
                                Decline
                              </button>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ================================================================ */}
          {/* TAB 7: LOCAL CALENDAR & MEASURABLE TASKS                          */}
          {/* ================================================================ */}
          {activeTab === 'calendar_tasks' && (
            <div className="space-y-6">
              {/* Header Telemetry row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="rounded-xl border border-scar/40 bg-abyss/85 p-4 flex items-center justify-between shadow-sm">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      Calendar Events
                    </h3>
                    <p className="text-2xl font-black font-mono text-bone mt-1">
                      {calendarEvents.length}
                    </p>
                  </div>
                  <span className="grid h-10 w-10 place-items-center rounded-lg bg-crimson/20 border border-crimson/40 text-amber-300">
                    <Icon name="spark" className="h-5 w-5 text-amber-400" />
                  </span>
                </div>

                <div className="rounded-xl border border-scar/40 bg-abyss/85 p-4 flex items-center justify-between shadow-sm">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      Measurable Tasks
                    </h3>
                    <p className="text-2xl font-black font-mono text-amber-300 mt-1">
                      {measurableTasks.length}
                    </p>
                  </div>
                  <span className="grid h-10 w-10 place-items-center rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400">
                    <Icon name="app" className="h-5 w-5" />
                  </span>
                </div>

                <div className="rounded-xl border border-scar/40 bg-abyss/85 p-4 flex items-center justify-between shadow-sm">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      System Mode
                    </h3>
                    <p className="text-xs font-mono text-emerald-400 flex items-center gap-1.5 mt-1 font-bold">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                      100% Local SQLite (No Google Calendar API)
                    </p>
                    <p className="text-[10px] font-mono text-ash mt-0.5">
                      Voice intents: "meetings this week" & "update progress"
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={fetchCalendarAndTasks}
                    className="grid h-8 w-8 place-items-center rounded border border-scar/40 bg-scar/20 text-ash hover:border-gold hover:text-white transition"
                    title="Refresh data"
                  >
                    <Icon name="refresh" className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {/* Two Column Grid: Left = Calendar, Right = Measurable Tasks */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {/* LEFT: CALENDAR EVENTS */}
                <div className="rounded-xl border border-scar/50 bg-[#120509]/90 p-5 space-y-4 shadow-lg flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between gap-3 border-b border-scar/30 pb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-sky-500/20 border border-sky-500/50 px-2 py-0.5 text-[10.5px] font-mono font-bold text-sky-300 uppercase">
                            CALENDAR
                          </span>
                          <h2 className="text-base font-bold text-bone">
                            Scheduled Meetings & Events
                          </h2>
                        </div>
                        <p className="text-xs font-mono text-ash mt-0.5">
                          Query via voice: "do I have any meetings this week"
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowEventForm((prev) => !prev)}
                        className="rounded-lg border border-amber-400/60 bg-amber-500/20 px-3 py-1.5 text-xs font-mono font-bold text-amber-300 hover:bg-amber-500/30 transition shadow-sm"
                      >
                        {showEventForm ? 'Cancel' : '+ Add Event'}
                      </button>
                    </div>

                    {/* Add Event Form */}
                    {showEventForm && (
                      <form onSubmit={handleCreateEvent} className="mt-4 p-3.5 rounded-xl border border-amber-400/40 bg-[#18050a] space-y-3 animate-fadeIn">
                        <h4 className="text-xs font-mono font-bold text-amber-300 uppercase">New Calendar Event</h4>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <input
                            type="text"
                            placeholder="Title (e.g. Thesis Advisory)"
                            value={newEventTitle}
                            onChange={(e) => setNewEventTitle(e.target.value)}
                            required
                            className="rounded-lg border border-scar/60 bg-abyss px-3 py-1.5 text-xs text-bone outline-none focus:border-amber-400 font-mono"
                          />
                          <select
                            value={newEventType}
                            onChange={(e) => setNewEventType(e.target.value)}
                            className="rounded-lg border border-scar/60 bg-abyss px-3 py-1.5 text-xs text-bone outline-none focus:border-amber-400 font-mono"
                          >
                            <option value="meeting">Meeting</option>
                            <option value="deadline">Deadline</option>
                            <option value="review">Review</option>
                            <option value="presentation">Presentation</option>
                          </select>
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="datetime-local"
                            value={newEventDate}
                            onChange={(e) => setNewEventDate(e.target.value)}
                            className="flex-1 rounded-lg border border-scar/60 bg-abyss px-3 py-1.5 text-xs text-bone outline-none focus:border-amber-400 font-mono"
                          />
                          <button
                            type="submit"
                            className="rounded-lg bg-crimson px-4 py-1.5 text-xs font-mono font-bold text-white hover:bg-rose-700 transition"
                          >
                            Save Event
                          </button>
                        </div>
                      </form>
                    )}

                    {/* Calendar Event Cards */}
                    <div className="mt-4 space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
                      {calendarEvents.length === 0 ? (
                        <div className="rounded-xl border border-scar/30 bg-abyss/50 p-8 text-center text-xs font-mono text-ash">
                          No calendar events recorded in SQLite yet. Add one above or say "do I have any meetings this week".
                        </div>
                      ) : (
                        calendarEvents.map((ev) => (
                          <div
                            key={ev.id}
                            className="rounded-xl border border-scar/40 bg-abyss/70 p-3 flex items-center justify-between gap-3 hover:border-gold/50 transition"
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="rounded bg-sky-500/20 border border-sky-500/50 px-2 py-0.5 text-[10px] font-mono font-bold text-sky-300 uppercase">
                                  {ev.event_type}
                                </span>
                                <h4 className="text-xs font-bold text-bone truncate">{ev.title}</h4>
                              </div>
                              <p className="text-[11px] font-mono text-ash mt-1 flex items-center gap-1.5">
                                <Icon name="spark" className="h-3 w-3 text-amber-400" />
                                <span>{ev.start_date ? new Date(ev.start_date).toLocaleString([], { month: 'short', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit' }) : 'No date'}</span>
                              </p>
                            </div>
                            <span className="text-[10px] font-mono text-ash/60 bg-scar/30 px-2 py-0.5 rounded">
                              ID: #{ev.id}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

                {/* RIGHT: MEASURABLE TASKS */}
                <div className="rounded-xl border border-scar/50 bg-[#120509]/90 p-5 space-y-4 shadow-lg flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between gap-3 border-b border-scar/30 pb-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-amber-500/20 border border-amber-500/50 px-2 py-0.5 text-[10.5px] font-mono font-bold text-amber-300 uppercase">
                            MEASURABLE TASKS
                          </span>
                          <h2 className="text-base font-bold text-bone">
                            Quantitative Progress Goals
                          </h2>
                        </div>
                        <p className="text-xs font-mono text-ash mt-0.5">
                          Voice: "write a 25 RRL" or "Update my 5 client progress to 2"
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setShowTaskForm((prev) => !prev)}
                        className="rounded-lg border border-amber-400/60 bg-amber-500/20 px-3 py-1.5 text-xs font-mono font-bold text-amber-300 hover:bg-amber-500/30 transition shadow-sm"
                      >
                        {showTaskForm ? 'Cancel' : '+ New Task'}
                      </button>
                    </div>

                    {/* Add Task Form */}
                    {showTaskForm && (
                      <form onSubmit={handleCreateTask} className="mt-4 p-3.5 rounded-xl border border-amber-400/40 bg-[#18050a] space-y-3 animate-fadeIn">
                        <h4 className="text-xs font-mono font-bold text-amber-300 uppercase">Create Measurable Goal</h4>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                          <input
                            type="text"
                            placeholder="Goal Title (e.g. RRL Review)"
                            value={newTaskTitle}
                            onChange={(e) => setNewTaskTitle(e.target.value)}
                            required
                            className="rounded-lg border border-scar/60 bg-abyss px-3 py-1.5 text-xs text-bone outline-none focus:border-amber-400 font-mono"
                          />
                          <input
                            type="number"
                            placeholder="Target (e.g. 25)"
                            value={newTaskTarget}
                            onChange={(e) => setNewTaskTarget(e.target.value)}
                            required
                            className="rounded-lg border border-scar/60 bg-abyss px-3 py-1.5 text-xs text-bone outline-none focus:border-amber-400 font-mono"
                          />
                          <input
                            type="text"
                            placeholder="Unit (e.g. pages, clients)"
                            value={newTaskUnit}
                            onChange={(e) => setNewTaskUnit(e.target.value)}
                            className="rounded-lg border border-scar/60 bg-abyss px-3 py-1.5 text-xs text-bone outline-none focus:border-amber-400 font-mono"
                          />
                        </div>
                        <div className="flex justify-end">
                          <button
                            type="submit"
                            className="rounded-lg bg-crimson px-4 py-1.5 text-xs font-mono font-bold text-white hover:bg-rose-700 transition"
                          >
                            Add Measurable Task
                          </button>
                        </div>
                      </form>
                    )}

                    {/* Measurable Tasks Cards with Progress Bars */}
                    <div className="mt-4 space-y-3 max-h-[460px] overflow-y-auto pr-1">
                      {measurableTasks.length === 0 ? (
                        <div className="rounded-xl border border-scar/30 bg-abyss/50 p-8 text-center text-xs font-mono text-ash">
                          No measurable progress tasks tracked yet. Try speaking "write a 25 RRL" or add one above.
                        </div>
                      ) : (
                        measurableTasks.map((task) => {
                          const pct = task.target_progress > 0
                            ? Math.round((task.current_progress / task.target_progress) * 100)
                            : 0
                          const isDone = task.current_progress >= task.target_progress && task.target_progress > 0

                          return (
                            <div
                              key={task.id}
                              className={`rounded-xl border p-4 transition shadow-sm space-y-2.5 ${
                                isDone
                                  ? 'border-emerald-500/60 bg-[#07160d]/90'
                                  : 'border-scar/40 bg-abyss/80 hover:border-gold/60'
                              }`}
                            >
                              <div className="flex items-center justify-between gap-3">
                                <div>
                                  <h4 className="text-sm font-bold text-bone">{task.title}</h4>
                                  <p className="text-[11px] font-mono text-ash">
                                    Target: <strong className="text-amber-200">{task.target_progress} {task.unit}</strong>
                                  </p>
                                </div>
                                <div className="text-right">
                                  <span className={`text-base font-black font-mono ${isDone ? 'text-emerald-400' : 'text-amber-300'}`}>
                                    {pct}%
                                  </span>
                                  <p className="text-[10.5px] font-mono text-ash">
                                    {task.current_progress} / {task.target_progress} {task.unit}
                                  </p>
                                </div>
                              </div>

                              {/* Smooth Progress Bar */}
                              <div className="h-2.5 w-full rounded-full bg-scar/40 overflow-hidden p-0.5 border border-scar/50">
                                <div
                                  className={`h-full rounded-full transition-all duration-300 ${
                                    isDone
                                      ? 'bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.5)]'
                                      : 'bg-gradient-to-r from-amber-500 via-rose-500 to-crimson'
                                  }`}
                                  style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                                />
                              </div>

                              {/* Progress Controls */}
                              <div className="flex items-center justify-between pt-1 border-t border-scar/20 text-xs font-mono">
                                <span className={`text-[10.5px] font-bold uppercase ${isDone ? 'text-emerald-400' : 'text-amber-300'}`}>
                                  {isDone ? 'Completed' : 'In Progress'}
                                </span>
                                <div className="flex items-center gap-1.5">
                                  <button
                                    type="button"
                                    onClick={() => handleAdjustTaskProgress(task, -1)}
                                    className="rounded border border-scar/50 bg-scar/20 px-2 py-0.5 text-ash hover:text-white hover:border-gold transition"
                                    title="Decrease progress by 1"
                                  >
                                    -1
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleAdjustTaskProgress(task, 1)}
                                    className="rounded border border-emerald-500/50 bg-emerald-950/40 px-2 py-0.5 text-emerald-300 hover:bg-emerald-900/50 transition font-bold"
                                    title="Increase progress by 1"
                                  >
                                    +1
                                  </button>
                                </div>
                              </div>
                            </div>
                          )
                        })
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
          {activeTab === 'emails' && (
            <div className="space-y-6">
              {/* Telemetry Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                <div className="rounded-xl border border-scar/40 bg-abyss/85 p-4 flex items-center justify-between shadow-sm">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      Total Priority Feed
                    </h3>
                    <p className="text-2xl font-black font-mono text-bone mt-1">
                      {priorityEmails.length}
                    </p>
                  </div>
                  <span className="grid h-10 w-10 place-items-center rounded-lg bg-crimson/20 border border-crimson/40 text-amber-300">
                    <Icon name="mail" className="h-5 w-5 text-amber-400" />
                  </span>
                </div>

                <div className="rounded-xl border border-scar/40 bg-abyss/85 p-4 flex items-center justify-between shadow-sm">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      Pending Action
                    </h3>
                    <p className={`text-2xl font-black font-mono mt-1 ${pendingCount > 0 ? 'text-rose-400 animate-pulse' : 'text-emerald-400'}`}>
                      {pendingCount}
                    </p>
                  </div>
                  <span className={`grid h-10 w-10 place-items-center rounded-lg border ${
                    pendingCount > 0
                      ? 'border-crimson/60 bg-crimson/25 text-rose-300 shadow-[0_0_12px_rgba(220,38,38,0.3)] animate-pulse'
                      : 'border-emerald-500/50 bg-emerald-950/30 text-emerald-400'
                  }`}>
                    <Icon name="bell" className="h-5 w-5" />
                  </span>
                </div>

                <div className="rounded-xl border border-scar/40 bg-abyss/85 p-4 flex items-center justify-between shadow-sm">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      Monitored Domains
                    </h3>
                    <div className="flex items-center gap-1.5 mt-2">
                      <span className="rounded bg-scar/30 px-1.5 py-0.5 text-[10px] font-mono text-white">Vercel</span>
                      <span className="rounded bg-scar/30 px-1.5 py-0.5 text-[10px] font-mono text-emerald-300">Supabase</span>
                      <span className="rounded bg-scar/30 px-1.5 py-0.5 text-[10px] font-mono text-amber-300">Anthropic</span>
                      <span className="rounded bg-scar/30 px-1.5 py-0.5 text-[10px] font-mono text-sky-300">Google</span>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-scar/40 bg-abyss/85 p-4 flex items-center justify-between shadow-sm">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      Pub/Sub Pipeline
                    </h3>
                    <p className="text-xs font-mono text-emerald-400 flex items-center gap-1.5 mt-1">
                      <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                      Streaming Pull Active
                    </p>
                    <p className="text-[10px] font-mono text-ash/80 mt-0.5">
                      Silent sync: 30s • {lastEmailSync ? lastEmailSync.toLocaleTimeString() : 'connecting...'}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => fetchPriorityEmails(false)}
                    disabled={isSyncingEmails}
                    className="grid h-8 w-8 place-items-center rounded border border-scar/40 bg-scar/20 text-ash hover:border-gold hover:text-white transition"
                    title="Manual refresh"
                  >
                    <Icon name="refresh" className={`h-4 w-4 ${isSyncingEmails ? 'animate-spin text-amber-400' : ''}`} />
                  </button>
                </div>
              </div>

              {/* Category Navigation Tabs */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-scar/40 pb-3.5 pt-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-mono font-bold uppercase text-ash tracking-wider mr-1">
                    VIEWS:
                  </span>
                  {[
                    { id: 'priority', label: 'Priority' },
                    { id: 'purchases', label: 'Purchases' },
                    { id: 'travel', label: 'Travel' },
                    { id: 'sent', label: 'Sent' },
                    { id: 'drafts', label: 'Drafts' },
                  ].map((cat) => {
                    const active = selectedCategory.toLowerCase() === cat.id
                    return (
                      <button
                        key={cat.id}
                        type="button"
                        onClick={() => handleSelectCategory(cat.id)}
                        className={`rounded-lg px-3.5 py-1.5 text-xs font-mono font-bold uppercase tracking-wider transition ${
                          active
                            ? 'bg-gradient-to-r from-crimson/50 to-crimson/20 border border-amber-400 text-amber-300 shadow-[0_0_15px_rgba(245,158,11,0.3)]'
                            : 'bg-scar/20 border border-scar/40 text-ash hover:text-white hover:border-scar/70 hover:bg-scar/30'
                        }`}
                      >
                        {cat.label}
                      </button>
                    )
                  })}
                </div>
                <div className="text-[11px] font-mono text-ash/80">
                  Active Category: <strong className="text-amber-300 uppercase">{selectedCategory}</strong>
                </div>
              </div>

              {/* Filter Controls Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-scar/30 pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-mono uppercase text-ash">Provider:</span>
                  {['ALL', 'PEOPLE', 'VERCEL', 'SUPABASE', 'ANTHROPIC', 'GOOGLE'].map((dom) => {
                    const count = dom === 'ALL'
                      ? priorityEmails.length
                      : dom === 'PEOPLE'
                      ? priorityEmails.filter((e) => getEmailDomainMeta(e.sender).isPerson).length
                      : priorityEmails.filter((e) => getEmailDomainMeta(e.sender).brand.toUpperCase().includes(dom)).length
                    return (
                      <button
                        key={dom}
                        type="button"
                        onClick={() => setEmailDomainFilter(dom)}
                        className={`rounded-md px-2.5 py-1 text-[11px] font-mono font-bold transition ${
                          emailDomainFilter === dom
                            ? 'bg-crimson/40 text-amber-300 border border-crimson/60 shadow-[0_0_10px_rgba(220,38,38,0.2)]'
                            : 'bg-scar/20 text-ash hover:text-white'
                        }`}
                      >
                        {dom} {count > 0 && `(${count})`}
                      </button>
                    )
                  })}
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono uppercase text-ash">Status:</span>
                  {['ALL', 'PENDING', 'READ'].map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setEmailStatusFilter(st)}
                      className={`rounded-md px-2.5 py-1 text-[11px] font-mono font-bold transition ${
                        emailStatusFilter === st
                          ? 'bg-gold/20 text-amber-300 border border-gold/40'
                          : 'bg-scar/20 text-ash hover:text-white'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => fetchPriorityEmails(false)}
                    disabled={isSyncingEmails}
                    className="flex items-center gap-1.5 rounded-md border border-scar/40 bg-abyss px-3 py-1 text-[11px] font-mono text-ash hover:border-gold hover:text-white transition ml-2"
                  >
                    <Icon name="refresh" className={`h-3 w-3 ${isSyncingEmails ? 'animate-spin text-amber-400' : ''}`} />
                    <span>REFRESH</span>
                  </button>
                </div>
              </div>

              {/* Email Cards Feed */}
              {filteredEmails.length === 0 ? (
                <div className="rounded-xl border border-scar/30 bg-abyss/60 p-12 text-center space-y-3">
                  <div className="grid h-12 w-12 mx-auto place-items-center rounded-full bg-crimson/20 border border-crimson/40 text-amber-400">
                    <Icon name="mail" className="h-6 w-6" />
                  </div>
                  <h4 className="text-sm font-mono font-bold text-bone">
                    No Priority Push Notifications Found
                  </h4>
                  <p className="text-xs font-mono text-ash max-w-md mx-auto">
                    The background GCP Pub/Sub listener is currently active on subscription <code className="text-amber-300 font-bold">nightmare-local-sub</code>. Real-time emails from Vercel, Supabase, Anthropic, and Google will automatically populate here via silent 30s background sync.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3.5">
                  {filteredEmails.map((email) => {
                    const meta = getEmailDomainMeta(email.sender)
                    const isPending = (email.status || 'Pending').toLowerCase() === 'pending'
                    const isBusy = emailActionBusyId === email.id

                    return (
                      <article
                        key={email.id || email.row_id}
                        className={`rounded-xl border p-4 transition shadow-md flex flex-col lg:flex-row lg:items-center justify-between gap-4 ${
                          isPending
                            ? 'border-crimson/70 bg-[#16060a]/90 hover:border-gold/70 shadow-[0_0_20px_rgba(220,38,38,0.18)]'
                            : 'border-scar/40 bg-abyss/80 hover:border-scar/80 opacity-85 hover:opacity-100'
                        }`}
                      >
                        <div className="min-w-0 flex-1 space-y-2">
                          <div className="flex flex-wrap items-center gap-2.5">
                            <span
                              className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-0.5 text-xs font-mono font-bold border ${meta.badgeClass}`}
                            >
                              <span>{meta.icon}</span>
                              <span>{meta.brand}</span>
                            </span>
                            <span className="rounded bg-gold/15 border border-gold/40 px-2 py-0.5 text-xs font-mono font-bold text-amber-300 uppercase">
                              {email.category ? email.category.toUpperCase() : 'PRIORITY'}
                            </span>
                            <span className="text-xs font-mono text-ash bg-scar/30 px-2 py-0.5 rounded">
                              ID: #{String(email.id).slice(-10)}
                            </span>
                            <StatusBadge status={email.status} />
                          </div>

                          <h3 className="text-sm font-bold text-bone leading-snug">
                            {email.subject || 'No Subject'}
                          </h3>

                          <div className="flex flex-wrap items-center gap-4 text-xs font-mono text-ash pt-1">
                            <span>
                              From: <strong className="text-bone/90">{email.sender}</strong>
                            </span>
                            <span className="text-ash/40">|</span>
                            <span className="text-ash/80">Domain: {meta.domain}</span>
                          </div>
                        </div>

                        <div className="shrink-0 flex lg:flex-col items-center justify-end gap-2">
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() => handleToggleEmailStatus(email)}
                            className={`rounded-lg border px-3.5 py-1.5 text-xs font-mono font-bold transition flex items-center gap-1.5 ${
                              isPending
                                ? 'border-emerald-500/70 bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 shadow-[0_0_10px_rgba(34,197,94,0.2)]'
                                : 'border-scar/40 bg-scar/20 text-ash hover:border-gold hover:text-white'
                            }`}
                            title={isPending ? 'Mark as Acknowledged / Read' : 'Mark as Pending'}
                          >
                            <Icon name="check" className="h-3.5 w-3.5" />
                            <span>{isPending ? 'Acknowledge' : 'Mark Pending'}</span>
                          </button>
                        </div>
                      </article>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* DEDICATED NOTIFICATION WIDGET OVERLAY (Quick Slide-Out Tray) */}
        {showEmailOverlay && (
          <aside
            className="absolute top-[60px] right-0 bottom-0 w-full sm:w-[520px] xl:w-[580px] z-50 flex flex-col bg-[#0b0306]/98 backdrop-blur-xl border-l border-scar/60 shadow-[-20px_0_60px_rgba(0,0,0,0.85)] font-sans"
          >
            {/* Drawer Header */}
            <div className="flex items-center justify-between border-b border-scar/40 px-5 py-3.5 bg-gradient-to-r from-[#170408] to-[#0f0407] shrink-0">
              <div className="flex items-center gap-2.5">
                <span className="grid h-7 w-7 place-items-center rounded bg-crimson/30 border border-crimson/60 text-amber-300 shadow-[0_0_10px_rgba(220,38,38,0.3)]">
                  <Icon name="mail" className="h-4 w-4 text-amber-400" />
                </span>
                <div>
                  <h2 className="text-xs font-mono font-extrabold uppercase tracking-widest text-bone">
                    REAL-TIME PRIORITY EMAIL FEED
                  </h2>
                  <div className="flex items-center gap-2 text-[10px] font-mono text-ash mt-0.5">
                    <span className="flex items-center gap-1 text-emerald-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      GCP PUB/SUB: ACTIVE
                    </span>
                    <span className="text-ash/40">•</span>
                    <span>SILENT SYNC: 30s</span>
                    {lastEmailSync && (
                      <>
                        <span className="text-ash/40">•</span>
                        <span className="text-ash/70">{lastEmailSync.toLocaleTimeString()}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fetchPriorityEmails(false)}
                  disabled={isSyncingEmails}
                  className="flex items-center gap-1 rounded border border-scar/40 bg-abyss/80 px-2 py-1 text-[11px] font-mono text-ash hover:border-gold hover:text-white transition"
                  title="Manual sync now"
                >
                  <Icon name="refresh" className={`h-3 w-3 ${isSyncingEmails ? 'animate-spin text-amber-400' : ''}`} />
                  <span>SYNC</span>
                </button>
                <button
                  type="button"
                  onClick={() => setShowEmailOverlay(false)}
                  className="grid h-7 w-7 place-items-center rounded border border-scar/40 bg-abyss/80 text-ash hover:border-crimson hover:text-white transition"
                  title="Close overlay"
                >
                  <Icon name="x" className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Drawer Category Filter Bar */}
            <div className="flex items-center gap-1.5 border-b border-scar/40 px-5 py-2 bg-[#120408] shrink-0 overflow-x-auto text-xs font-mono">
              <span className="text-[10.5px] uppercase font-bold text-ash mr-1">Views:</span>
              {[
                { id: 'priority', label: 'Priority' },
                { id: 'purchases', label: 'Purchases' },
                { id: 'travel', label: 'Travel' },
                { id: 'sent', label: 'Sent' },
                { id: 'drafts', label: 'Drafts' },
              ].map((cat) => {
                const active = selectedCategory.toLowerCase() === cat.id
                return (
                  <button
                    key={cat.id}
                    type="button"
                    onClick={() => handleSelectCategory(cat.id)}
                    className={`rounded px-2.5 py-1 text-[10.5px] font-mono font-bold uppercase transition ${
                      active
                        ? 'bg-crimson/50 text-amber-300 border border-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.25)]'
                        : 'bg-scar/20 text-ash hover:text-white border border-scar/30'
                    }`}
                  >
                    {cat.label}
                  </button>
                )
              })}
            </div>

            {/* Quick Filter Row */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-scar/30 px-5 py-2.5 bg-[#0e0407] shrink-0 text-xs font-mono">
              <div className="flex flex-wrap items-center gap-1.5">
                {['ALL', 'PEOPLE', 'VERCEL', 'SUPABASE', 'ANTHROPIC', 'GOOGLE'].map((dom) => {
                  const count = dom === 'ALL'
                    ? priorityEmails.length
                    : dom === 'PEOPLE'
                    ? priorityEmails.filter((e) => getEmailDomainMeta(e.sender).isPerson).length
                    : priorityEmails.filter((e) => getEmailDomainMeta(e.sender).brand.toUpperCase().includes(dom)).length
                  return (
                    <button
                      key={dom}
                      type="button"
                      onClick={() => setEmailDomainFilter(dom)}
                      className={`rounded px-2 py-0.5 text-[10.5px] font-bold transition ${
                        emailDomainFilter === dom
                          ? 'bg-crimson/40 text-amber-300 border border-crimson/60 shadow-[0_0_8px_rgba(220,38,38,0.2)]'
                          : 'bg-scar/20 text-ash hover:text-white'
                      }`}
                    >
                      {dom} {count > 0 && `(${count})`}
                    </button>
                  )
                })}
              </div>

              <div className="flex items-center gap-1">
                {['ALL', 'PENDING', 'READ'].map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setEmailStatusFilter(st)}
                    className={`rounded px-2 py-0.5 text-[10px] font-bold transition ${
                      emailStatusFilter === st
                        ? 'bg-gold/20 text-amber-300 border border-gold/40'
                        : 'text-ash/60 hover:text-white'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>

            {/* Email Cards Stream */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {filteredEmails.length === 0 ? (
                <div className="rounded-xl border border-scar/30 bg-abyss/70 p-8 text-center space-y-2">
                  <div className="grid h-10 w-10 mx-auto place-items-center rounded-full bg-crimson/20 border border-crimson/40 text-amber-400">
                    <Icon name="mail" className="h-5 w-5" />
                  </div>
                  <p className="text-xs font-mono font-bold text-bone">
                    No priority push notifications found.
                  </p>
                  <p className="text-[11px] font-mono text-ash/80 max-w-sm mx-auto">
                    GCP Pub/Sub subscriber is active on nightmare-local-sub. Incoming notifications from Vercel, Supabase, Anthropic, or Google update silently here every 30s.
                  </p>
                </div>
              ) : (
                filteredEmails.map((email) => {
                  const meta = getEmailDomainMeta(email.sender)
                  const isPending = (email.status || 'Pending').toLowerCase() === 'pending'
                  const isBusy = emailActionBusyId === email.id

                  return (
                    <article
                      key={email.id || email.row_id}
                      className={`rounded-xl border p-3.5 transition shadow-sm flex flex-col justify-between gap-2.5 ${
                        isPending
                          ? 'border-crimson/60 bg-[#16060a]/90 hover:border-gold/60 shadow-[0_0_15px_rgba(220,38,38,0.15)]'
                          : 'border-scar/30 bg-abyss/70 hover:border-scar/60 opacity-80 hover:opacity-100'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span
                            className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono font-bold border ${meta.badgeClass}`}
                          >
                            <span>{meta.icon}</span>
                            <span>{meta.brand}</span>
                          </span>
                          <span className="rounded bg-gold/15 border border-gold/40 px-2 py-0.5 text-[10px] font-mono font-bold text-amber-300 uppercase">
                            {email.category ? email.category.toUpperCase() : 'PRIORITY'}
                          </span>
                        </div>
                        <StatusBadge status={email.status} />
                      </div>

                      <h3 className="text-xs font-bold text-bone leading-snug line-clamp-2">
                        {email.subject || 'No Subject'}
                      </h3>

                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-scar/20 pt-2 text-[11px] font-mono text-ash">
                        <span className="truncate max-w-[280px]" title={email.sender}>
                          From: <strong className="text-bone/80">{email.sender}</strong>
                        </span>
                        <span className="text-[10px] text-ash/60">
                          ID: #{String(email.id).slice(-8)}
                        </span>
                      </div>

                      <div className="flex items-center justify-end gap-2 border-t border-scar/20 pt-2">
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => handleToggleEmailStatus(email)}
                          className={`rounded border px-2.5 py-1 text-[10.5px] font-mono font-bold transition flex items-center gap-1 ${
                            isPending
                              ? 'border-emerald-500/60 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-900/50'
                              : 'border-scar/40 bg-scar/20 text-ash hover:text-white'
                          }`}
                          title={isPending ? 'Mark as Read' : 'Mark as Pending'}
                        >
                          <Icon name="check" className="h-3 w-3" />
                          <span>{isPending ? 'Mark Read' : 'Mark Pending'}</span>
                        </button>
                      </div>
                    </article>
                  )
                })
              )}
            </div>
          </aside>
        )}
      </section>
    </div>
  )
}
