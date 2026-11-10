import { useEffect, useRef, useState } from 'react'
import Icon from './Icon'
import Terminal from './Terminal'

export default function ConversationWindow({ entries, busy, elapsed, onSpeak, onClose }) {
  const windowRef = useRef(null)
  const [closing, setClosing] = useState(false)
  const requestClose = () => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) onClose()
    else setClosing(true)
  }
  useEffect(() => {
    if (!closing) return
    const timer = setTimeout(onClose, 180)
    return () => clearTimeout(timer)
  }, [closing, onClose])
  useEffect(() => {
    const dialog = windowRef.current
    dialog.showModal()
    return () => dialog.close()
  }, [])

  const backdropClick = (event) => {
    if (event.target !== event.currentTarget) return
    const bounds = event.currentTarget.getBoundingClientRect()
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) requestClose()
  }

  const containFocus = (event) => {
    if (event.key !== 'Tab') return
    const controls = [...windowRef.current.querySelectorAll('button:not(:disabled), a[href], [tabindex="0"]')]
    const first = controls[0]
    const last = controls.at(-1)
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }

  return (
    <dialog ref={windowRef} className={`conversation-window ${closing ? 'is-closing' : ''}`} aria-labelledby="conversation-title" onCancel={(event) => { event.preventDefault(); requestClose() }} onClick={backdropClick} onKeyDown={containFocus}>
      <div className="reply-heading"><div><strong id="conversation-title">Conversation history</strong><p className="conversation-subtitle">The complete conversation so far</p></div>
        <button type="button" aria-label="Close conversation history" onClick={requestClose} autoFocus><Icon name="close" size={18} /></button>
      </div>
      <Terminal entries={entries} busy={busy} elapsed={elapsed} onSpeak={onSpeak} />
    </dialog>
  )
}
