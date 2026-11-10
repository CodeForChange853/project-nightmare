import { useEffect, useMemo, useState } from 'react'
import { splitSentences } from '../utils/useSpeech'
import { lyricLines, nextWordEnd } from '../utils/speechProgress'

function ResponseText({ answer, progress, text }) {
  const lines = useMemo(() => lyricLines(text), [text])
  const [position, setPosition] = useState(progress?.charIndex ?? 0)
  const [silentLine, setSilentLine] = useState(0)
  const timed = !progress || progress.status === 'error'

  useEffect(() => {
    if (progress && progress.status !== 'cancelled') setPosition((prev) => Math.max(prev, progress.charIndex))
  }, [progress?.charIndex, progress?.status])

  useEffect(() => {
    if (progress?.status !== 'speaking') return
    // Browser voices without boundary events still advance at a readable pace.
    const timer = setInterval(() => setPosition((prev) => Math.min(progress.sentenceEnd ?? text.length, nextWordEnd(text, prev))), 500 / (progress.rate || 1))
    return () => clearInterval(timer)
  }, [progress?.status, progress?.rate, progress?.sentenceEnd, text])

  const spokenLine = Math.max(0, lines.findIndex((line) => position <= line.end))
  const index = timed ? silentLine : progress.status === 'complete' ? lines.length - 1 : spokenLine

  useEffect(() => {
    if (progress?.status === 'error') setSilentLine(spokenLine)
  }, [progress?.status])

  useEffect(() => {
    if (!timed || silentLine >= lines.length - 1) return
    // Muted, unsupported, or failed speech keeps the same single-line format.
    const timer = setTimeout(() => setSilentLine((line) => line + 1), Math.max(2400, (lines[silentLine]?.words || 1) * 420))
    return () => clearTimeout(timer)
  }, [timed, silentLine, lines])

  return (
    <div className={`floating-response ${answer.ok === false || answer.role === 'system' ? 'is-error' : ''}`} role="region" aria-label="Current response">
      <p key={index} className="floating-response-text">{lines[index]?.text || text}</p>
    </div>
  )
}

export default function FloatingResponse({ answer, speechProgress }) {
  const text = splitSentences(answer.text).join(' ')
  const progress = speechProgress?.text === text && speechProgress.startedAt >= (answer.createdAt ?? 0) ? speechProgress : null
  return <ResponseText key={`${answer.id}:${progress?.id ?? 'silent'}`} answer={answer} progress={progress} text={text} />
}
