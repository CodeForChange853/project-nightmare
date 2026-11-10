import { useEffect, useRef, useState } from 'react'
import { MeetingCapture } from '../utils/meetingCapture'
import { translateMeeting } from '../api'

export default function SpeechPanel({ mode, speaker, onClose }) {
  const [source, setSource] = useState('mic')
  const [state, setState] = useState('stopped')
  const [error, setError] = useState('')
  const [interim, setInterim] = useState('')
  const [rows, setRows] = useState([])
  const [automatic, setAutomatic] = useState(true)
  const capture = useRef(null)
  const nextId = useRef(0)
  const inFlight = useRef(false)
  const request = useRef(null)
  const alive = useRef(false)
  const bottom = useRef(null)
  const meeting = mode === 'meeting'
  const running = state !== 'stopped'
  const pending = rows.filter((row) => row.status === 'pending').length

  useEffect(() => {
    const keydown = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', keydown)
    return () => window.removeEventListener('keydown', keydown)
  }, [onClose])

  useEffect(() => {
    alive.current = true
    capture.current = new MeetingCapture({
      onFinal: (text) => {
        const pieces = text.match(/[\s\S]{1,1000}/g) || []
        setRows((prev) => [...prev, ...pieces.map((part) => ({
          id: ++nextId.current, text: part, time: new Date().toLocaleTimeString(), status: 'pending',
        }))])
      },
      onInterim: setInterim, onState: setState, onError: setError,
    })
    return () => {
      alive.current = false
      capture.current?.stop()
      request.current?.abort()
    }
  }, [])

  useEffect(() => {
    if (rows.length >= 2000 && running) {
      capture.current.stop()
      setError('Transcript limit reached. Export and clear the transcript before continuing.')
    }
    bottom.current?.scrollIntoView({ block: 'nearest' })
  }, [rows.length, interim, running])

  useEffect(() => {
    if (!automatic || inFlight.current) return
    const row = rows.find((item) => item.status === 'pending')
    if (!row) return
    inFlight.current = true
    const controller = new AbortController()
    request.current = controller
    setRows((prev) => prev.map((r) => r.id === row.id ? { ...r, status: 'translating' } : r))
    translateMeeting(row.text, controller.signal).then(({ translation }) => {
      if (alive.current) setRows((prev) => prev.map((r) => r.id === row.id ? { ...r, translation, status: 'done' } : r))
    }).catch((err) => {
      if (!alive.current || controller.signal.aborted) return
      setRows((prev) => prev.map((r) => r.id === row.id ? { ...r, status: 'failed' } : r))
      setError(err.message)
      setAutomatic(false)
    }).finally(() => {
      inFlight.current = false
      // A state update after clearing the lock lets the next queued row start.
      if (alive.current) setRows((prev) => [...prev])
    })
  }, [rows, automatic])

  const download = () => {
    const text = rows.map((r) => `[${r.time}] ${r.text}\n${r.translation || `[${r.status}]`}`).join('\n\n')
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `nightmare-meeting-${new Date().toISOString().replaceAll(':', '-')}.txt`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const field = 'rounded-lg border border-scar bg-abyss p-2 text-bone'
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4">
      <section role="dialog" aria-modal="true" aria-label={meeting ? 'Live meeting captions' : 'Voice settings'} className="flex max-h-[90vh] w-full max-w-4xl flex-col gap-4 overflow-y-auto rounded-2xl border border-scar bg-abyss p-6 text-bone">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-xl">{meeting ? 'Mandarin meeting · Chinese + English' : 'Nightmare voice'}</h2>
          <button className={field} onClick={onClose} autoFocus>Close</button>
        </div>
        {!meeting ? <>
          <p>Choose a free browser voice and preview it. Natural voices appear first when your browser provides them.</p>
          <label className="flex flex-col gap-2">Voice
            <select className={field} value={speaker.voiceURI} onChange={(e) => { speaker.cancel(); speaker.setVoiceURI(e.target.value) }}>
              <option value="">Automatic · best available {speaker.voiceGender} English voice</option>
              {speaker.voiceURI && !speaker.voices.some((v) => v.voiceURI === speaker.voiceURI) && <option value={speaker.voiceURI}>Saved voice unavailable · using automatic</option>}
              {[...speaker.voices].sort((a, b) => Number(/natural|neural|online|google/i.test(b.name)) - Number(/natural|neural|online|google/i.test(a.name))).map((v) => <option key={v.voiceURI} value={v.voiceURI}>{v.name} · {v.lang}{v.localService ? ' · device' : ' · online'}</option>)}
            </select>
          </label>
          <label>Speed · {speaker.rate.toFixed(2)}x <input className="ml-3" type="range" min="0.7" max="1.5" step="0.05" value={speaker.rate} onChange={(e) => speaker.setRate(e.target.value)} /></label>
          <div className="flex gap-3"><button className={field} disabled={speaker.muted} onClick={() => speaker.say('Hello Adrian. I am ready to help. This is how my voice sounds at a natural pitch.')}>Preview voice</button><button className={field} onClick={speaker.toggleMute}>{speaker.muted ? 'Unmute' : 'Mute'}</button><button className={field} onClick={speaker.cancel}>Stop voice</button></div>
          <p className="text-sm text-smoke">No voice download or paid API is required. Online voices need internet; a browser may expose only basic installed voices.</p>
        </> : <>
          <p className="text-sm text-smoke">Live Chinese captions use your browser's speech service, which may send audio online. English translations send finalized text to your existing agy account and may lag behind speech. Captions stay in this panel; export before closing. Let participants know you are transcribing.</p>
          <div className="flex flex-wrap items-center gap-3">
            <label>Audio <select className={field} value={source} disabled={running} onChange={(e) => setSource(e.target.value)}><option value="mic">Microphone · nearby speakers</option><option value="pc">PC / meeting tab audio</option><option value="both">PC audio + microphone</option></select></label>
            <button className={field} disabled={running || rows.length >= 2000} onClick={() => { setError(''); speaker.cancel(); capture.current.start(source) }}>Start captions</button>
            <button className={field} disabled={!running} onClick={() => capture.current.stop()}>Stop</button>
            <span role="status">{state} · {pending} awaiting translation</span>
          </div>
          <p className="text-sm text-smoke">For PC audio, use desktop Chrome 135+ and enable Share audio in the picker. A browser meeting tab is usually easiest. Headphones help prevent duplicate audio when mixing the microphone.</p>
          <div className="flex flex-wrap gap-3">
            <label><input type="checkbox" checked={automatic} onChange={(e) => setAutomatic(e.target.checked)} /> Translate to English</label>
            <button className={field} onClick={() => { setError(''); setRows((prev) => prev.map((r) => r.status === 'failed' ? { ...r, status: 'pending' } : r)); setAutomatic(true) }}>Retry translations</button>
            <button className={field} disabled={!rows.length} onClick={download}>Export transcript</button>
            <button className={field} disabled={running || inFlight.current} onClick={() => setRows([])}>Clear</button>
          </div>
          {error && <p role="alert" className="text-red-300">{error}</p>}
          <div className="min-h-48 overflow-y-auto rounded-xl border border-scar p-4" aria-live="polite" aria-relevant="additions text">
            {!rows.length && !interim && <p className="text-smoke">Chinese captions will appear here. Meeting speech never runs commands.</p>}
            {rows.map((row) => <article key={row.id} className="mb-4 border-b border-scar/40 pb-3"><time className="text-xs text-smoke">{row.time}</time><p lang="zh-CN" className="text-lg">{row.text}</p><p lang="en" className="mt-1 text-ash">{row.translation || (row.status === 'failed' ? 'Translation failed · retry above' : row.status === 'translating' ? 'Translating…' : 'Awaiting translation…')}</p></article>)}
            {interim && <p lang="zh-CN" className="text-lg text-smoke">{interim}</p>}<div ref={bottom} />
          </div>
        </>}
      </section>
    </div>
  )
}
