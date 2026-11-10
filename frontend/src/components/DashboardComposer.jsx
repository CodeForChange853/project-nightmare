import { useEffect, useId, useRef, useState } from 'react'
import { SLASH_COMMANDS } from '../slashCommands'
import Icon from './Icon'

export default function DashboardComposer({ disabled, listening, interim, canTalk, onPressStart, onPressEnd, onSubmit, speaking, onStopSpeaking, readonly, speechError }) {
  const [draft, setDraft] = useState('')
  const [pick, setPick] = useState(0)
  const [dismissed, setDismissed] = useState(false)
  const input = useRef(null)
  const listId = useId()
  const typed = draft.trimStart()
  const suggestions = typed.startsWith('/') && !/\s/.test(typed) && !dismissed
    ? SLASH_COMMANDS.filter((c) => c.name.startsWith(typed.toLowerCase()) && !(readonly && ['/voice', '/meeting', '/transcribe', '/settings', '/defense'].includes(c.name)))
    : []
  const selected = Math.min(pick, Math.max(0, suggestions.length - 1))

  useEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(112, el.scrollHeight)}px`
  }, [draft])

  const send = (text) => {
    if (disabled || listening || !text.trim()) return
    onSubmit(text.trim())
    setDraft('')
    setPick(0)
    setDismissed(false)
    input.current?.focus()
  }

  const onKeyDown = (e) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return
    if (suggestions.length && ['ArrowDown', 'ArrowUp'].includes(e.key)) {
      e.preventDefault()
      setPick((selected + (e.key === 'ArrowDown' ? 1 : -1) + suggestions.length) % suggestions.length)
    } else if (suggestions.length && e.key === 'Tab') {
      e.preventDefault()
      setDraft(suggestions[selected].name)
    } else if (e.key === 'Escape' && suggestions.length) {
      e.preventDefault()
      e.stopPropagation()
      setDismissed(true)
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(suggestions.length ? (suggestions.find((c) => c.name === typed.toLowerCase()) ?? suggestions[selected]).name : draft)
    }
  }

  return (
    <div className="dashboard-composer" data-dashboard-composer>
      <div className="composer-toolbar">
        <span className="composer-hint">{listening ? 'Release to send your voice command' : 'Enter to send · Shift+Enter for a new line · / commands'}</span>
        <div className="flex items-center gap-3">
          {!readonly && <>
            <button type="button" disabled={disabled || listening} onClick={() => onSubmit('/meeting')}>Meeting</button>
            <button type="button" disabled={disabled || listening} onClick={() => onSubmit('/voice')}>Voice settings</button>
          </>}
          {speaking && <button type="button" className="text-ember" onClick={onStopSpeaking}>Stop speaking</button>}
        </div>
      </div>
      {listening && <p className="composer-transcript" role="status">{interim || 'Listening… speak now'}</p>}
      <div className="relative">
        {suggestions.length > 0 && (
          <ul id={listId} role="listbox" aria-label="Commands" className="dashboard-suggestions">
            {suggestions.map((c, i) => (
              <li key={c.name} id={`${listId}-${i}`} role="option" aria-selected={i === selected}>
                <button type="button" tabIndex={-1} onMouseDown={(e) => e.preventDefault()} onMouseEnter={() => setPick(i)} onClick={() => send(c.name)}>
                  <span className="font-mono text-ember">{c.name}</span><span className="text-ash">{c.hint}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <form className="composer-field" onSubmit={(e) => { e.preventDefault(); send(draft) }}>
          <textarea
            ref={input} value={draft} rows={1} aria-label="Command"
            aria-describedby={`${listId}-hint`}
            aria-controls={suggestions.length ? listId : undefined}
            aria-activedescendant={suggestions.length ? `${listId}-${selected}` : undefined}
            aria-autocomplete="list"
            onChange={(e) => { setDraft(e.target.value); setPick(0); setDismissed(false) }}
            onKeyDown={onKeyDown} placeholder="Ask Nightmare or type / for commands…"
            autoFocus autoComplete="off" spellCheck={false}
          />
          <button type="button" className={`composer-mic ${listening ? 'is-listening' : ''}`} disabled={!canTalk}
            aria-label="Hold microphone to talk" title="Hold to talk, or hold Space outside the input"
            onPointerDown={(e) => { if (e.button !== 0 || !canTalk) return; e.currentTarget.setPointerCapture(e.pointerId); onPressStart() }}
            onPointerUp={onPressEnd} onPointerCancel={onPressEnd} onLostPointerCapture={onPressEnd}
            onContextMenu={(e) => e.preventDefault()}>
            <Icon name="mic" size={19} />
          </button>
          <button type="submit" className="composer-send" disabled={disabled || listening || !draft.trim()} aria-label="Send command" title="Send command">
            <Icon name="send" size={19} />
          </button>
        </form>
      </div>
      {speechError && <p className="mt-2 text-xs text-bile" role="status">Microphone: {speechError}</p>}
      <span id={`${listId}-hint`} className="sr-only">Enter sends. Shift+Enter adds a new line. Type slash to browse commands. Use arrow keys to choose a command and Tab to complete it.</span>
    </div>
  )
}
