import Icon, { Sigil } from './Icon'

export default function StatusBar({ status, locked, lastAsked, onLogout, onRetry }) {
  const online = Boolean(status)
  const readonly = status?.role === 'readonly'
  return (
    <header className="flex items-center justify-between gap-3 px-4 py-3 lg:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <Sigil size={34} className="shrink-0 drop-shadow-[0_0_12px_rgba(220,20,60,0.55)]" />
        <div className="leading-none">
          <p className="font-display text-[19px] font-extrabold uppercase tracking-[0.22em] text-bone">Nightmare</p>
          <p className="mt-1 text-[11px] text-smoke">Local voice agent</p>
        </div>
      </div>

      {lastAsked && (
        <p className="glass hidden max-w-[42ch] truncate rounded-full px-4 py-1.5 text-[12px] text-ash md:block" title={lastAsked}>
          <span className="text-smoke">You asked </span>
          <span className="text-bone">{lastAsked}</span>
        </p>
      )}

      <div className="flex shrink-0 items-center gap-2">
        {readonly && (
          <span
            className="rounded-full border border-bile/40 bg-bile/10 px-2.5 py-1 text-[11px] text-bile"
            title="Phone PIN session: Nightmare can read and answer, but cannot open or run anything"
          >
            Read-only
          </span>
        )}
        {online ? (
          <span className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] text-ash">
            <span className="pulse-dot h-2 w-2 rounded-full bg-crimson" />
            Online
            <span className="hidden text-smoke sm:inline">with {status.llm}</span>
          </span>
        ) : locked ? (
          <span className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] text-ash">
            <Icon name="lock" size={13} /> Locked
          </span>
        ) : (
          <button
            type="button"
            onClick={onRetry}
            className="glass flex items-center gap-2 rounded-full px-3 py-1.5 text-[12px] text-ember hover:text-bone"
          >
            <span className="h-2 w-2 rounded-full bg-smoke" />
            Backend offline
            <Icon name="refresh" size={13} />
          </button>
        )}
        {status?.auth_mode === 'session' && (
          <button
            type="button"
            onClick={onLogout}
            title="Lock Nightmare"
            aria-label="Lock Nightmare"
            className="glass grid h-8 w-8 place-items-center rounded-full text-ash hover:text-ember"
          >
            <Icon name="lock" size={15} />
          </button>
        )}
      </div>
    </header>
  )
}
