import { useCallback, useEffect, useRef, useState } from 'react'
import { getDefenseSessions } from '../api'
import Icon from './Icon'

export default function DefensePanel({
  open,
  data,
  status,
  onClose,
  onCommand,
}) {
  const [sessions, setSessions] = useState([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const root = useRef(null)

  const activePacing = data?.status ? data : status?.defense
  const isRunning = activePacing && activePacing.status !== 'inactive'

  const refreshHistory = useCallback(async () => {
    try {
      setLoadingSessions(true)
      const res = await getDefenseSessions(8)
      if (res?.ok && Array.isArray(res.sessions)) {
        setSessions(res.sessions)
      }
    } catch {
      // ignore
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      refreshHistory()
    }
  }, [open, refreshHistory])

  if (!open) return null

  const formatTime = (secs) => {
    if (secs == null || secs < 0) return '0:00'
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}:${s < 10 ? '0' : ''}${s}`
  }

  const pacingBadge = (pStatus) => {
    if (pStatus === 'over_budget') {
      return (
        <span className="rounded-full border border-crimson bg-crimson/20 px-3 py-1 text-[11px] font-bold text-ember uppercase animate-pulse">
          Over Budget
        </span>
      )
    }
    if (pStatus === 'nearing_limit') {
      return (
        <span className="rounded-full border border-amber-500 bg-amber-500/20 px-3 py-1 text-[11px] font-bold text-amber-300 uppercase">
          Nearing Limit
        </span>
      )
    }
    return (
      <span className="rounded-full border border-emerald-500/50 bg-emerald-500/20 px-3 py-1 text-[11px] font-bold text-emerald-400 uppercase">
        On Pace
      </span>
    )
  }

  return (
    <div
      ref={root}
      role="dialog"
      aria-label="Academic Thesis Defense Co-Pilot"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/80 backdrop-blur-md"
      onClick={(e) => {
        if (e.target === root.current) onClose()
      }}
    >
      <div className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-scar/60 bg-gradient-to-b from-[#18090d] to-[#0c0406] shadow-[0_0_50px_rgba(220,20,60,0.35)]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-scar/40 px-5 py-4">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-crimson/20 text-ember border border-crimson/40">
              <Icon name="presentation" size={20} />
            </span>
            <div>
              <h2 className="font-display text-base font-bold uppercase tracking-wider text-bone flex items-center gap-2">
                Defense Co-Pilot
                <span className="rounded-full bg-scar/40 px-2 py-0.5 text-[10px] text-smoke font-normal">Phase 8F</span>
              </h2>
              <p className="text-[12px] text-smoke">CitizenGraph Academic Defense & Mock Panelist Interrogation</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid h-8 w-8 place-items-center rounded-full text-smoke hover:bg-scar/30 hover:text-bone transition"
            aria-label="Close"
          >
            <Icon name="close" size={16} />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Active Defense Session HUD */}
          {isRunning ? (
            <div className="rounded-xl border border-scar/50 bg-black/40 p-4 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="h-3 w-3 rounded-full bg-emerald-500 animate-ping" />
                  <span className="font-mono text-sm font-bold text-bone">LIVE REHEARSAL ACTIVE</span>
                </div>
                {pacingBadge(activePacing.status)}
              </div>

              {/* Timer & Slide Metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
                <div className="rounded-lg bg-scar/20 p-2.5">
                  <p className="text-[11px] text-smoke uppercase tracking-wider">Total Elapsed</p>
                  <p className="font-mono text-xl font-bold text-bone">{formatTime(activePacing.elapsed_seconds)}</p>
                </div>
                <div className="rounded-lg bg-scar/20 p-2.5">
                  <p className="text-[11px] text-smoke uppercase tracking-wider">Budget Remaining</p>
                  <p className="font-mono text-xl font-bold text-ember">{formatTime(activePacing.remaining_seconds)}</p>
                </div>
                <div className="rounded-lg bg-scar/20 p-2.5">
                  <p className="text-[11px] text-smoke uppercase tracking-wider">Current Slide</p>
                  <p className="font-mono text-xl font-bold text-bone">
                    {activePacing.slide} <span className="text-xs text-smoke font-normal">/ {activePacing.total_slides || 10}</span>
                  </p>
                </div>
                <div className="rounded-lg bg-scar/20 p-2.5">
                  <p className="text-[11px] text-smoke uppercase tracking-wider">Slide Time</p>
                  <p className="font-mono text-xl font-bold text-bone">{formatTime(activePacing.slide_elapsed_seconds)}</p>
                </div>
              </div>

              {/* Pacing Advice Banner */}
              {activePacing.advice && (
                <div className="rounded-lg border border-scar/40 bg-scar/15 px-4 py-2.5 text-xs text-ash">
                  <span className="font-bold text-bone">Pacing Advice:</span> {activePacing.advice}
                </div>
              )}

              {/* Quick Slide & Defense Navigation Controls */}
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => onCommand?.('previous slide')}
                  className="rounded-lg border border-scar/40 bg-scar/20 px-3 py-1.5 text-xs text-bone hover:border-scar hover:bg-scar/40 transition flex items-center gap-1.5"
                >
                  <Icon name="back" size={14} /> Prev Slide
                </button>
                <button
                  type="button"
                  onClick={() => onCommand?.('next slide')}
                  className="rounded-lg border border-scar/40 bg-scar/20 px-3 py-1.5 text-xs text-bone hover:border-scar hover:bg-scar/40 transition flex items-center gap-1.5"
                >
                  Next Slide <Icon name="chevron" size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => onCommand?.('ask defense question')}
                  className="rounded-lg border border-crimson/60 bg-crimson/20 px-3 py-1.5 text-xs text-amber-300 hover:border-crimson hover:bg-crimson/40 transition flex items-center gap-1.5"
                >
                  <Icon name="spark" size={14} /> Panelist Question
                </button>
                <button
                  type="button"
                  onClick={() => onCommand?.('defense timing')}
                  className="rounded-lg border border-scar/40 bg-scar/20 px-3 py-1.5 text-xs text-smoke hover:text-bone transition flex items-center gap-1.5"
                >
                  <Icon name="gauge" size={14} /> Check Pacing
                </button>
                <button
                  type="button"
                  onClick={() => onCommand?.('stop defense rehearsal')}
                  className="ml-auto rounded-lg border border-crimson/80 bg-crimson/30 px-3 py-1.5 text-xs text-ember hover:bg-crimson/50 transition font-bold"
                >
                  Stop Rehearsal
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-scar/50 bg-black/30 p-6 text-center space-y-3">
              <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-scar/20 text-smoke">
                <Icon name="presentation" size={24} />
              </div>
              <div>
                <h3 className="font-display text-sm font-bold uppercase tracking-wider text-bone">No Defense Rehearsal In Progress</h3>
                <p className="mt-1 text-xs text-smoke max-w-md mx-auto">
                  Launch PowerPoint COM slide-aware defense mode. Nightmare will track your 12-minute presentation budget, monitor slide targets, and simulate academic panelist questions.
                </p>
              </div>
              <div className="pt-2 flex justify-center gap-3">
                <button
                  type="button"
                  onClick={() => onCommand?.('start defense rehearsal')}
                  className="rounded-xl border border-gold/70 bg-gradient-to-r from-crimson/50 to-gold/30 px-5 py-2 text-xs font-bold uppercase tracking-wider text-amber-200 hover:brightness-110 shadow-[0_0_15px_rgba(255,209,102,0.3)] transition"
                >
                  Start Defense Rehearsal (Level 5)
                </button>
                <button
                  type="button"
                  onClick={() => onCommand?.('ask defense question')}
                  className="rounded-xl border border-scar/60 bg-scar/20 px-4 py-2 text-xs text-bone hover:bg-scar/40 transition"
                >
                  Ask Sample Question
                </button>
              </div>
            </div>
          )}

          {/* Active Question Display if just asked */}
          {data?.question && (
            <div className="rounded-xl border border-crimson/50 bg-crimson/10 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-300">
                  <Icon name="spark" size={14} /> Mock Panelist Question
                </span>
                {data.slide && (
                  <span className="text-[11px] text-smoke">Slide {data.slide} {data.topic ? `â€¢ ${data.topic}` : ''}</span>
                )}
              </div>
              <p className="font-serif text-sm italic leading-relaxed text-bone sm:text-base">
                "{data.question}"
              </p>
            </div>
          )}

          {/* Past Rehearsal History Table */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-smoke flex items-center gap-1.5">
                <Icon name="log" size={13} /> Defense Rehearsal History
              </h3>
              <button
                type="button"
                onClick={refreshHistory}
                disabled={loadingSessions}
                className="text-[11px] text-smoke hover:text-bone flex items-center gap-1 transition"
              >
                <Icon name="refresh" size={11} className={loadingSessions ? 'animate-spin' : ''} /> Refresh
              </button>
            </div>

            {sessions.length === 0 ? (
              <p className="rounded-lg border border-scar/20 bg-black/20 p-3 text-center text-xs text-smoke">
                No past defense sessions logged yet. Complete a rehearsal to view pacing metrics.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-scar/30 bg-black/30">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-scar/30 text-[10px] uppercase text-smoke bg-scar/10">
                      <th className="px-3 py-2">Date</th>
                      <th className="px-3 py-2">Presentation</th>
                      <th className="px-3 py-2 text-center">Duration</th>
                      <th className="px-3 py-2 text-center">Slides</th>
                      <th className="px-3 py-2 text-center">Questions</th>
                      <th className="px-3 py-2">Outcome</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-scar/20">
                    {sessions.map((s) => (
                      <tr key={s.id} className="hover:bg-scar/10 transition">
                        <td className="px-3 py-2 text-smoke whitespace-nowrap">
                          {s.ts ? s.ts.slice(0, 16).replace('T', ' ') : 'â€”'}
                        </td>
                        <td className="px-3 py-2 font-medium text-bone truncate max-w-[140px]">
                          {s.presentation_name}
                        </td>
                        <td className="px-3 py-2 text-center font-mono text-ash whitespace-nowrap">
                          {formatTime(s.duration_seconds)}
                        </td>
                        <td className="px-3 py-2 text-center text-smoke">{s.slides_count}</td>
                        <td className="px-3 py-2 text-center text-smoke">{s.questions_count}</td>
                        <td className="px-3 py-2">
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                              s.pacing_summary?.includes('Over')
                                ? 'bg-crimson/20 text-ember'
                                : 'bg-emerald-500/20 text-emerald-400'
                            }`}
                          >
                            {s.pacing_summary || 'Completed'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-scar/40 bg-black/40 px-5 py-3 text-[11px] text-smoke">
          <span>Voice Commands: "next slide", "panelist question", "defense timing", "stop rehearsal"</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-scar/40 bg-scar/20 px-3 py-1 text-bone hover:bg-scar/40 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
