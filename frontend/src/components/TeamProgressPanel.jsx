import { useEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import Icon from './Icon'
import {
  openTimelineInExcel,
  syncTimelineBaseline,
  getTimelineDiff,
} from '../api'

const GDRIVE_URL =
  'https://drive.google.com/drive/folders/1P4CWnBnYfLkkGKnrAswe9lwX5HcCQYDg?usp=sharing'

function StatusBadge({ status }) {
  const norm = (status || 'Pending').toLowerCase()
  if (norm.includes('complete') || norm.includes('done')) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-mono font-bold tracking-wide border border-[#22c55e] bg-[rgba(22,163,74,0.18)] text-[#4ade80] shadow-[0_0_10px_rgba(34,197,94,0.15)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#4ade80]" />
        COMPLETED
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

export default function TeamProgressPanel({
  data,
  initialTab = 'summary',
  pendingAction,
  onApprove,
  onDecline,
  onClose,
  onRefresh,
}) {
  const panelRef = useRef(null)
  const contentRef = useRef(null)

  const [activeTab, setActiveTab] = useState(initialTab === 'diff' ? 'diff' : 'summary')
  const [roadmapFilter, setRoadmapFilter] = useState('ALL')
  const [wbsPhaseFilter, setWbsPhaseFilter] = useState('ALL')
  const [wbsStatusFilter, setWbsStatusFilter] = useState('ALL')
  const [feedback, setFeedback] = useState(null)
  const [busyAction, setBusyAction] = useState(false)

  // Sync initial tab when changed from props
  useEffect(() => {
    if (initialTab === 'diff') setActiveTab('diff')
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

  const roadmap = data?.roadmap || []
  const wbs = data?.wbs || []
  const objectives = data?.objectives || []
  const dashboard = data?.dashboard || {}
  const diff = data?.diff || {}
  const quotas = data?.quotas || []
  const staleTasks = data?.stale_tasks || []
  const fileName = data?.file_name || 'CitizenGraph_Thesis_Timeline_2026_2027-v2.xlsx'

  const p1 = dashboard?.phase_1 || { total: 12, completed: 0, in_progress: 0, pending: 12, completion_pct: 0 }
  const p2 = dashboard?.phase_2 || { total: 9, completed: 0, in_progress: 0, pending: 9, completion_pct: 0 }
  const rSummary = dashboard?.roadmap || { total: 9, completed: 0, in_progress: 0, pending: 9, completion_pct: 0 }
  const wbsSummary = dashboard?.overall_wbs || { total: 21, completed: 0, in_progress: 0, pending: 21, completion_pct: 0 }
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

  // Filtered Roadmap
  const filteredRoadmap = roadmap.filter((s) => {
    if (roadmapFilter === 'COMPLETED') return s.status === 'Completed'
    if (roadmapFilter === 'IN PROGRESS') return s.status === 'In Progress'
    if (roadmapFilter === 'PENDING') return s.status === 'Pending'
    if (roadmapFilter === 'PHASE 1') return (s.phase || '').toLowerCase().includes('phase 1')
    if (roadmapFilter === 'PHASE 2') return (s.phase || '').toLowerCase().includes('phase 2')
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
    return matchPhase && matchStatus
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
        {/* TOP COMMAND HEADER BAR */}
        <header className="flex flex-wrap items-center justify-between border-b border-scar/40 px-6 py-3.5 bg-gradient-to-r from-[#170408] via-[#0f0407] to-[#170408] shrink-0 gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-crimson/25 border border-crimson/50 text-gold shadow-[0_0_15px_rgba(220,38,38,0.3)]">
              <Icon name="spark" className="h-5 w-5 text-amber-400" />
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2.5">
                <h1 className="text-base font-extrabold tracking-widest text-bone font-mono uppercase">
                  CITIZEN GRAPH // THESIS & DEV TELEMETRY
                </h1>
                <span className="rounded-full bg-crimson/40 border border-crimson/60 px-2.5 py-0.5 text-[10px] font-mono font-bold text-amber-300 uppercase tracking-widest shadow-[0_0_10px_rgba(251,191,36,0.2)]">
                  LEVEL 5 ARCHITECT
                </span>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-ash mt-0.5">
                <span className="flex items-center gap-1.5 text-emerald-400/90">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  LOCAL FILE: Connected ({fileName})
                </span>
                <span className="text-ash/40">|</span>
                <a
                  href={GDRIVE_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-gold/90 hover:text-white transition underline decoration-gold/40 hover:decoration-gold"
                  title="Open Shared Google Drive Folder"
                >
                  <Icon name="external" className="h-3.5 w-3.5" />
                  GDRIVE SHARED LINK: Linked
                </a>
              </div>
            </div>
          </div>

          {/* Quick Header Action Buttons */}
          <div className="flex items-center gap-2.5 shrink-0">
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
            <button
              type="button"
              disabled={busyAction}
              onClick={() => setActiveTab('diff')}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11.5px] font-mono font-bold transition shadow-sm ${
                diff.has_changes
                  ? 'border-amber-400 bg-amber-500/20 text-amber-300 shadow-[0_0_15px_rgba(245,158,11,0.25)] animate-pulse'
                  : 'border-scar/40 bg-abyss/80 text-ash hover:border-amber-400/80 hover:text-white'
              }`}
              title="Inspect changes against baseline"
            >
              <Icon name="spark" className="h-3.5 w-3.5 text-amber-400" />
              DIFF CHANGES {diff.has_changes && `(${diff.change_count})`}
            </button>
            <button
              type="button"
              disabled={busyAction}
              onClick={handleOpenExcel}
              className="flex items-center gap-1.5 rounded-lg border border-scar/40 bg-abyss/80 px-3 py-1.5 text-[11.5px] font-mono font-bold text-ash transition hover:border-emerald-400/80 hover:text-white"
              title="Open master workbook in Microsoft Excel on desktop"
            >
              <Icon name="external" className="h-3.5 w-3.5 text-emerald-400" />
              OPEN IN EXCEL
            </button>
            <button
              type="button"
              disabled={busyAction}
              onClick={handleSyncBaseline}
              className="flex items-center gap-1.5 rounded-lg border border-scar/40 bg-abyss/80 px-3 py-1.5 text-[11.5px] font-mono font-bold text-gold transition hover:border-gold hover:bg-gold/15"
              title="Acknowledge & commit current workbook state as baseline"
            >
              <Icon name="check" className="h-3.5 w-3.5 text-gold" />
              SYNC BASELINE
            </button>
            <button
              type="button"
              onClick={onClose}
              className="grid h-8 w-8 place-items-center rounded-lg border border-scar/40 bg-abyss/80 text-ash transition hover:border-crimson hover:text-white"
              title="Close panel"
            >
              <Icon name="x" className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* 5-TAB NAVIGATION BAR (Desktop Single Active Tab View) */}
        <nav
          className="flex items-center gap-2 px-6 py-2.5 border-b border-scar/30 bg-[#0c0407] shrink-0 overflow-x-auto"
          role="tablist"
        >
          {[
            { id: 'summary', label: '1. EXECUTIVE SUMMARY' },
            { id: 'roadmap', label: '2. 8-MONTH ROADMAP', badge: roadmap.length },
            { id: 'wbs', label: '3. PHASE 1 & 2 WEEKLY WBS', badge: wbs.length },
            { id: 'objectives', label: '4. OBJECTIVES & KPIs', badge: objectives.length },
            {
              id: 'diff',
              label: '5. GDRIVE DIFF & TEAM SYNC',
              badge: diff.has_changes ? `${diff.change_count} NEW` : null,
              pulse: diff.has_changes,
            },
          ].map((tab) => {
            const active = activeTab === tab.id
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={active}
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-mono font-bold uppercase tracking-wider transition ${
                  active
                    ? 'border border-crimson/80 bg-gradient-to-r from-crimson/35 to-crimson/15 text-amber-300 shadow-[0_0_20px_rgba(220,38,38,0.25)]'
                    : 'border border-transparent text-ash/80 hover:text-white hover:border-scar/40 hover:bg-scar/15'
                }`}
              >
                <span>{tab.label}</span>
                {tab.badge && (
                  <span
                    className={`rounded-full px-2 py-0.2 text-[10px] font-mono font-bold ${
                      tab.pulse
                        ? 'bg-amber-500 text-black animate-pulse'
                        : active
                        ? 'bg-crimson/60 text-amber-200'
                        : 'bg-scar/40 text-ash'
                    }`}
                  >
                    {tab.badge}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        {/* MAIN BODY: RENDERS ONLY ONE ACTIVE TAB (Full Screen Real Estate) */}
        <div ref={contentRef} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* ================================================================ */}
          {/* TAB 1: EXECUTIVE SUMMARY                                        */}
          {/* ================================================================ */}
          {activeTab === 'summary' && (
            <div className="space-y-6">
              {/* Hero Phase Cards */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {/* Phase 1 Hero Card */}
                <div className="relative rounded-xl border border-scar/50 bg-[#120509]/90 p-5 shadow-lg flex flex-col justify-between">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-sky-500/20 border border-sky-500/50 px-2 py-0.5 text-[10.5px] font-mono font-bold text-sky-300 uppercase">
                          PHASE 1
                        </span>
                        <h2 className="text-base font-bold text-bone">
                          Chapters 1-3 & Core Dev
                        </h2>
                      </div>
                      <p className="text-xs font-mono text-ash/90 mt-1">
                        Timeline: Sept - 2nd Week of Dec 2026 | Focus: Domain Ontology, QLoRA AST Guardrails, Neo4j Graph
                      </p>
                    </div>
                    <span className="rounded-full bg-crimson/30 border border-crimson/50 px-3 py-1 text-[11px] font-mono font-bold text-rose-300 whitespace-nowrap">
                      Deadline: {p1.deadline}
                    </span>
                  </div>

                  <div className="my-5">
                    <div className="flex items-end justify-between mb-2">
                      <span className="text-xs font-mono text-ash uppercase tracking-wider">
                        Phase 1 Progress Rollup
                      </span>
                      <span className="text-2xl font-black font-mono text-sky-400">
                        {p1.completion_pct}%
                      </span>
                    </div>
                    {/* Segmented Progress Track (12 tasks) */}
                    <div className="grid grid-cols-12 gap-1.5 h-3">
                      {Array.from({ length: 12 }).map((_, i) => {
                        const isDone = i < p1.completed
                        const isProg = !isDone && i < p1.completed + p1.in_progress
                        return (
                          <div
                            key={i}
                            className={`rounded-sm transition-all ${
                              isDone
                                ? 'bg-emerald-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]'
                                : isProg
                                ? 'bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(251,191,36,0.4)]'
                                : 'bg-scar/40 border border-scar/60'
                            }`}
                            title={`WBS 1.${i + 1}`}
                          />
                        )
                      })}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-scar/30 pt-3 text-xs font-mono">
                    <div className="flex items-center gap-3">
                      <span className="text-emerald-400 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-emerald-400" />
                        Completed: {p1.completed}
                      </span>
                      <span className="text-amber-400 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-amber-400" />
                        In Progress: {p1.in_progress}
                      </span>
                      <span className="text-rose-400 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-rose-400" />
                        Pending: {p1.pending}
                      </span>
                    </div>
                    <span className="text-ash/70">Total Tasks: {p1.total}</span>
                  </div>
                </div>

                {/* Phase 2 Hero Card */}
                <div className="relative rounded-xl border border-scar/50 bg-[#120509]/90 p-5 shadow-lg flex flex-col justify-between">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-teal-500/20 border border-teal-500/50 px-2 py-0.5 text-[10.5px] font-mono font-bold text-teal-300 uppercase">
                          PHASE 2
                        </span>
                        <h2 className="text-base font-bold text-bone">
                          Evaluation & Chapters 4-6
                        </h2>
                      </div>
                      <p className="text-xs font-mono text-ash/90 mt-1">
                        Timeline: Dec W3, 2026 - Feb 2027 | Focus: Benchmark Testing, User Validation, Final Thesis Defense
                      </p>
                    </div>
                    <span className="rounded-full bg-crimson/30 border border-crimson/50 px-3 py-1 text-[11px] font-mono font-bold text-rose-300 whitespace-nowrap">
                      Deadline: {p2.deadline}
                    </span>
                  </div>

                  <div className="my-5">
                    <div className="flex items-end justify-between mb-2">
                      <span className="text-xs font-mono text-ash uppercase tracking-wider">
                        Phase 2 Progress Rollup
                      </span>
                      <span className="text-2xl font-black font-mono text-teal-400">
                        {p2.completion_pct}%
                      </span>
                    </div>
                    {/* Segmented Progress Track (9 tasks) */}
                    <div className="grid grid-cols-9 gap-1.5 h-3">
                      {Array.from({ length: 9 }).map((_, i) => {
                        const isDone = i < p2.completed
                        const isProg = !isDone && i < p2.completed + p2.in_progress
                        return (
                          <div
                            key={i}
                            className={`rounded-sm transition-all ${
                              isDone
                                ? 'bg-emerald-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]'
                                : isProg
                                ? 'bg-amber-400 animate-pulse shadow-[0_0_8px_rgba(251,191,36,0.4)]'
                                : 'bg-scar/40 border border-scar/60'
                            }`}
                            title={`WBS 2.${i + 1}`}
                          />
                        )
                      })}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-scar/30 pt-3 text-xs font-mono">
                    <div className="flex items-center gap-3">
                      <span className="text-emerald-400 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-emerald-400" />
                        Completed: {p2.completed}
                      </span>
                      <span className="text-amber-400 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-amber-400" />
                        In Progress: {p2.in_progress}
                      </span>
                      <span className="text-rose-400 flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-rose-400" />
                        Pending: {p2.pending}
                      </span>
                    </div>
                    <span className="text-ash/70">Total Tasks: {p2.total}</span>
                  </div>
                </div>
              </div>

              {/* Overall Project Telemetry */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-scar/40 bg-abyss/80 p-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      General 8-Month Roadmap Stages
                    </h3>
                    <p className="text-lg font-bold text-bone mt-0.5">
                      {rSummary.completed} of {rSummary.total} Stages Complete
                    </p>
                  </div>
                  <div className="text-right font-mono">
                    <span className="text-2xl font-bold text-amber-300">
                      {rSummary.completion_pct}%
                    </span>
                  </div>
                </div>
                <div className="rounded-xl border border-scar/40 bg-abyss/80 p-4 flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-mono uppercase text-ash tracking-wider">
                      Overall Detailed WBS Execution
                    </h3>
                    <p className="text-lg font-bold text-bone mt-0.5">
                      {wbsSummary.completed} of {wbsSummary.total} Total Tasks Complete
                    </p>
                  </div>
                  <div className="text-right font-mono">
                    <span className="text-2xl font-bold text-amber-300">
                      {wbsSummary.completion_pct}%
                    </span>
                  </div>
                </div>
              </div>

              {/* Chapter 1 Quantitative Benchmark Targets */}
              <div className="rounded-xl border border-scar/40 bg-abyss/80 p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-scar/30 pb-3">
                  <div>
                    <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-amber-400 flex items-center gap-2">
                      <Icon name="spark" className="h-4 w-4 text-amber-400" />
                      Chapter 1 Specific Objectives: Quantitative Benchmark Targets (SO-4 to SO-7)
                    </h3>
                    <p className="text-[11.5px] font-mono text-ash/80 mt-0.5">
                      Target metrics evaluated against Calbayog City LGU citizen procedural datasets
                    </p>
                  </div>
                  <span className="text-[11px] font-mono text-gold bg-gold/10 border border-gold/30 px-2 py-0.5 rounded">
                    6 Key KPI Gauges
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                  {targets.map((tg, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-scar/30 bg-[#120609] p-3.5 flex flex-col justify-between space-y-2.5 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-crimson/40 text-amber-300 border border-crimson/60">
                              {tg.id}
                            </span>
                            <span className="text-xs font-bold text-bone line-clamp-1">
                              {tg.name}
                            </span>
                          </div>
                          <p className="text-[11px] font-mono text-ash/80 mt-1">
                            {tg.component}
                          </p>
                        </div>
                        <StatusBadge status={tg.status} />
                      </div>

                      <div className="flex items-center justify-between border-t border-scar/20 pt-2 text-xs font-mono">
                        <span className="text-ash/70">Target KPI:</span>
                        <span className="font-bold text-amber-300 bg-amber-400/10 border border-amber-400/30 px-2 py-0.5 rounded">
                          {tg.target}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
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
                  Chapter 1 Specific Objectives & Architectural Component Alignment
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
                    Accept & Commit as Baseline
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
                    All 9 roadmap stages, 21 WBS tasks, and 7 specific objectives match the stored state.
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
        </div>
      </section>
    </div>
  )
}
