import { useCallback, useEffect, useRef, useState } from 'react'
import { mergeTranscripts } from './transcript.js'
import { nextWordEnd } from './speechProgress.js'

const Recognition =
  typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null

export const recognitionSupported = Boolean(Recognition)
export const synthesisSupported = typeof window !== 'undefined' && 'speechSynthesis' in window

const RELEASE_GRACE_MS = 350
const LANG_OPTIONS = ['en-PH', 'en-US']
const SPEED_OPTIONS = [0.9, 1.0, 1.15, 1.3, 1.5]

const MALE_HINTS = /david|mark|james|george|guy|christopher|eric|roger|ryan|steffan|daniel|alex|male/i
const FEMALE_HINTS = /zira|aria|jenny|sonia|natasha|clara|rosa|hazel|susan|catherine|samantha|google us english|female/i

export function pickVoice(voices, gender, voiceURI = '') {
  const selected = voices.find((v) => v.voiceURI === voiceURI)
  if (selected) return selected
  const enVoices = voices.filter((v) => /^en([-_]|$)/i.test(v.lang))
  const pool = [...(enVoices.length > 0 ? enVoices : voices)].sort((a, b) => {
    const score = (v) => /natural|neural|online/i.test(v.name) ? 3 : /google/i.test(v.name) ? 2 : 0
    return score(b) - score(a)
  })
  if (!pool.length) return null
  if (gender === 'male') {
    return (
      pool.find((v) => MALE_HINTS.test(v.name) && !/female/i.test(v.name)) ||
      pool.find((v) => !FEMALE_HINTS.test(v.name)) ||
      pool[0]
    )
  }
  return (
    pool.find((v) => FEMALE_HINTS.test(v.name)) ||
    pool.find((v) => !MALE_HINTS.test(v.name)) ||
    pool[0]
  )
}

export function splitSentences(text) {
  const clean = String(text || '')
    .replace(/[`*_#>-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!clean) return []

  const regex = /[^.!?]+[.!?]+(?=\s+|$)|[^.!?]+$/g
  const matches = clean.match(regex)
  if (!matches) return [clean]
  return matches.map((s) => s.trim()).filter(Boolean)
}

/** Progressive sentence chunking buffer matching /[.!?]\s+/ for first-sentence streaming TTS */
export class ProgressiveSentenceChunker {
  constructor(onSentence) {
    this.buffer = ''
    this.onSentence = onSentence
  }

  push(textChunk) {
    if (!textChunk) return
    this.buffer += String(textChunk)
    const regex = /[.!?]\s+/g
    let lastIndex = 0
    let match

    while ((match = regex.exec(this.buffer)) !== null) {
      const sentence = this.buffer.slice(lastIndex, match.index + 1).trim()
      lastIndex = match.index + match[0].length
      if (sentence && this.onSentence) {
        this.onSentence(sentence)
      }
    }

    if (lastIndex > 0) {
      this.buffer = this.buffer.slice(lastIndex)
    }
  }

  flush() {
    const remaining = this.buffer.trim()
    this.buffer = ''
    if (remaining && this.onSentence) {
      this.onSentence(remaining)
    }
  }
}

/** Push-to-talk speech recognition (Google Web Speech-to-Text in Chrome). */
export function useRecognizer({ onFinal }) {
  const recRef = useRef(null)
  const stopTimerRef = useRef(null)
  const textRef = useRef('')
  const gotResultRef = useRef(false)
  const onFinalRef = useRef(onFinal)
  onFinalRef.current = onFinal

  const [lang, setLang] = useState(() => {
    try {
      const saved = localStorage.getItem('nightmare.lang')
      return LANG_OPTIONS.includes(saved) ? saved : 'en-PH'
    } catch {
      return 'en-PH'
    }
  })
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')

  const toggleLang = useCallback(() => {
    setLang((prev) => {
      const next = prev === 'en-PH' ? 'en-US' : 'en-PH'
      try {
        localStorage.setItem('nightmare.lang', next)
      } catch {
        /* ignore storage errors */
      }
      return next
    })
  }, [])

  const start = useCallback(() => {
    if (!Recognition) return
    if (stopTimerRef.current) {
      clearTimeout(stopTimerRef.current)
      stopTimerRef.current = null
    }
    if (recRef.current) return
    const rec = new Recognition()
    rec.lang = lang
    rec.interimResults = true
    rec.continuous = true
    rec.maxAlternatives = 1
    textRef.current = ''
    gotResultRef.current = false

    rec.onresult = (event) => {
      gotResultRef.current = true
      // Android repeats the growing phrase in every result; mergeTranscripts keeps one copy
      const text = mergeTranscripts(Array.from(event.results, (r) => r[0].transcript))
      textRef.current = text
      setInterim(text)
    }
    rec.onerror = (event) => {
      if (event.error === 'no-speech') {
        setError('no speech heard â€” check mic input or hold Space a moment longer')
      } else if (event.error !== 'aborted') {
        setError(event.error)
      }
    }
    rec.onend = () => {
      if (stopTimerRef.current) {
        clearTimeout(stopTimerRef.current)
        stopTimerRef.current = null
      }
      recRef.current = null
      setListening(false)
      setInterim('')
      const text = textRef.current.trim()
      textRef.current = ''
      if (text) {
        setError('')
        onFinalRef.current?.(text)
      } else if (!gotResultRef.current) {
        setError((prev) => prev || 'no speech heard ” hold Space while speaking (use Google Chrome)')
      }
    }

    try {
      rec.start()
      recRef.current = rec
      setError('')
      setListening(true)
    } catch (err) {
      setError(String(err))
    }
  }, [lang])

  const stop = useCallback(() => {
    if (!recRef.current || stopTimerRef.current) return
    stopTimerRef.current = setTimeout(() => {
      stopTimerRef.current = null
      recRef.current?.stop()
    }, RELEASE_GRACE_MS)
  }, [])

  const cancel = useCallback(() => {
    if (stopTimerRef.current) clearTimeout(stopTimerRef.current)
    stopTimerRef.current = null
    const rec = recRef.current
    recRef.current = null
    textRef.current = ''
    if (rec) {
      rec.onend = null
      rec.onresult = null
      rec.onerror = null
      rec.abort()
    }
    setListening(false)
    setInterim('')
  }, [])

  useEffect(
    () => () => {
      if (stopTimerRef.current) clearTimeout(stopTimerRef.current)
      recRef.current?.abort?.()
    },
    [],
  )

  return { listening, interim, error, lang, toggleLang, start, stop, cancel, supported: recognitionSupported }
}

/** Text-to-speech with persisted mute, male/female voice selector, speed control, and full-text sentence chunking. */
export function useSpeaker() {
  const [speaking, setSpeaking] = useState(false)
  const [speechProgress, setSpeechProgress] = useState(null)
  const speechRunRef = useRef(0)
  const [voices, setVoices] = useState([])
  const [voiceURI, setVoiceURIState] = useState(() => {
    try { return localStorage.getItem('nightmare.voiceURI') || '' } catch { return '' }
  })
  const voiceURIRef = useRef(voiceURI)
  voiceURIRef.current = voiceURI
  const setVoiceURI = useCallback((value) => {
    voiceURIRef.current = value
    setVoiceURIState(value)
    try { localStorage.setItem('nightmare.voiceURI', value) } catch { /* storage unavailable */ }
  }, [])
  const [muted, setMuted] = useState(() => {
    try {
      return localStorage.getItem('nightmare.muted') === '1'
    } catch {
      return false
    }
  })
  const [voiceGender, setVoiceGenderState] = useState(() => {
    try {
      return localStorage.getItem('nightmare.voiceGender') === 'female' ? 'female' : 'male'
    } catch {
      return 'male'
    }
  })
  const [rate, setRateState] = useState(() => {
    try {
      const saved = parseFloat(localStorage.getItem('nightmare.voiceRate') || '1.0')
      return SPEED_OPTIONS.includes(saved) ? saved : 1.0
    } catch {
      return 1.0
    }
  })

  const mutedRef = useRef(muted)
  const genderRef = useRef(voiceGender)
  const rateRef = useRef(rate)
  const voicesRef = useRef(voices)
  const pendingCountRef = useRef(0)
  const chunkerRef = useRef(null)
  mutedRef.current = muted
  genderRef.current = voiceGender
  rateRef.current = rate
  voicesRef.current = voices

  useEffect(() => {
    if (!synthesisSupported) return
    const loadVoices = () => {
      const available = window.speechSynthesis.getVoices() || []
      if (available.length) setVoices(available)
    }
    loadVoices()
    window.speechSynthesis.addEventListener?.('voiceschanged', loadVoices)
    return () => window.speechSynthesis.removeEventListener?.('voiceschanged', loadVoices)
  }, [])

  const cancel = useCallback(() => {
    speechRunRef.current++
    pendingCountRef.current = 0
    if (chunkerRef.current) chunkerRef.current = null
    setSpeaking(false)
    setSpeechProgress((prev) => prev ? { ...prev, status: 'cancelled', charIndex: prev.text.length } : null)
    if (synthesisSupported) window.speechSynthesis.cancel()
  }, [])

  const speakSentence = useCallback((sentence, overrideOpts = {}, caption = null) => {
    if (!synthesisSupported || mutedRef.current || !sentence) return
    const targetGender = overrideOpts.gender || genderRef.current
    const targetRate = overrideOpts.rate || rateRef.current
    const available = voicesRef.current.length
      ? voicesRef.current
      : window.speechSynthesis.getVoices() || []
    const chosenVoice = pickVoice(available, targetGender, overrideOpts.gender ? '' : voiceURIRef.current)

    pendingCountRef.current++
    setSpeaking(true)

    const utterance = new SpeechSynthesisUtterance(sentence)
    if (chosenVoice) {
      utterance.voice = chosenVoice
      utterance.lang = chosenVoice.lang
    }
    utterance.rate = targetRate
    utterance.pitch = 1

    const meta = caption ?? { id: speechRunRef.current, text: sentence, offset: 0, startedAt: performance.now() }
    let settled = false
    const advance = (index, status = 'speaking') => {
      if (meta.id !== speechRunRef.current || settled) return
      setSpeechProgress((prev) => ({ id: meta.id, text: meta.text, rate: targetRate, status, startedAt: meta.startedAt, sentenceEnd: meta.offset + sentence.length,
        charIndex: Math.max(prev?.id === meta.id && prev.text === meta.text ? prev.charIndex : 0, index) }))
    }
    utterance.onstart = () => advance(nextWordEnd(meta.text, meta.offset))
    utterance.onboundary = (event) => advance(nextWordEnd(meta.text, meta.offset + (event.charIndex || 0)))

    const handleDone = (error = false) => {
      if (meta.id !== speechRunRef.current || settled) return
      advance(meta.offset + sentence.length, error ? 'error' : pendingCountRef.current <= 1 ? 'complete' : 'speaking')
      settled = true
      pendingCountRef.current = Math.max(0, pendingCountRef.current - 1)
      if (pendingCountRef.current === 0) {
        setSpeaking(false)
      }
    }
    utterance.onend = () => handleDone()
    utterance.onerror = () => handleDone(true)

    // Speak immediately: first sentence begins audio playback right away,
    // subsequent sentences queue seamlessly in the browser's speech synthesis engine
    try { window.speechSynthesis.speak(utterance) }
    catch { handleDone(true) }
  }, [])

  const say = useCallback((text, overrideOpts = {}) => {
    if (!synthesisSupported || mutedRef.current || !text) return
    const chunks = splitSentences(text)
    if (!chunks.length) return

    const id = ++speechRunRef.current
    const startedAt = performance.now()
    pendingCountRef.current = 0
    chunkerRef.current = null
    window.speechSynthesis.cancel()
    const captionText = chunks.join(' ')
    setSpeechProgress({ id, text: captionText, startedAt, sentenceEnd: chunks[0].length, charIndex: nextWordEnd(captionText), status: 'queued', rate: overrideOpts.rate || rateRef.current })

    // Progressive sentence queueing: first sentence speaks immediately, rest queue
    let offset = 0
    chunks.forEach((sentence) => {
      speakSentence(sentence, overrideOpts, { id, text: captionText, offset, startedAt })
      offset += sentence.length + 1
    })
  }, [speakSentence])

  const enqueueChunk = useCallback((chunk, overrideOpts = {}) => {
    if (!synthesisSupported || mutedRef.current) return
    if (!chunkerRef.current) {
      chunkerRef.current = new ProgressiveSentenceChunker((sentence) => {
        speakSentence(sentence, overrideOpts)
      })
    }
    chunkerRef.current.push(chunk)
  }, [speakSentence])

  const flushSpeech = useCallback(() => {
    if (chunkerRef.current) {
      chunkerRef.current.flush()
      chunkerRef.current = null
    }
  }, [])

  const setVoiceGender = useCallback((nextGender) => {
    const clean = nextGender === 'female' ? 'female' : 'male'
    setVoiceGenderState(clean)
    setVoiceURI('')
    genderRef.current = clean
    try {
      localStorage.setItem('nightmare.voiceGender', clean)
    } catch {
      /* ignore */
    }
  }, [setVoiceURI])

  const toggleVoiceGender = useCallback(() => {
    const next = genderRef.current === 'male' ? 'female' : 'male'
    setVoiceGender(next)
  }, [setVoiceGender])

  const setRate = useCallback((nextRate) => {
    const clean = Math.max(0.7, Math.min(1.8, Number(nextRate) || 1.0))
    setRateState(clean)
    rateRef.current = clean
    try {
      localStorage.setItem('nightmare.voiceRate', String(clean))
    } catch {
      /* ignore */
    }
  }, [])

  const cycleRate = useCallback(() => {
    const idx = SPEED_OPTIONS.indexOf(rateRef.current)
    const next = SPEED_OPTIONS[(idx + 1) % SPEED_OPTIONS.length]
    setRate(next)
  }, [setRate])

  const toggleMute = useCallback(() => {
    const next = !mutedRef.current
    mutedRef.current = next
    setMuted(next)
    try { localStorage.setItem('nightmare.muted', next ? '1' : '0') } catch { /* storage unavailable */ }
    if (next) cancel()
  }, [cancel])

  return {
    voices,
    voiceURI,
    setVoiceURI,
    speaking,
    speechProgress,
    muted,
    voiceGender,
    rate,
    say,
    cancel,
    enqueueChunk,
    flushSpeech,
    toggleMute,
    toggleVoiceGender,
    setVoiceGender,
    cycleRate,
    setRate,
  }
}
