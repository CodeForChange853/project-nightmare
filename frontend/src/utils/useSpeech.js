import { useCallback, useEffect, useRef, useState } from 'react'
import { mergeTranscripts } from './transcript'

const Recognition =
  typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null

export const recognitionSupported = Boolean(Recognition)
export const synthesisSupported = typeof window !== 'undefined' && 'speechSynthesis' in window

const RELEASE_GRACE_MS = 350
const LANG_OPTIONS = ['en-PH', 'en-US']
const SPEED_OPTIONS = [0.9, 1.0, 1.15, 1.3, 1.5]

const MALE_HINTS = /david|mark|james|george|guy|christopher|eric|roger|ryan|steffan|daniel|alex|male/i
const FEMALE_HINTS = /zira|aria|jenny|sonia|natasha|clara|rosa|hazel|susan|catherine|samantha|google us english|female/i

function pickVoice(voices, gender) {
  const enVoices = voices.filter((v) => /^en([-_]|$)/i.test(v.lang))
  const pool = enVoices.length > 0 ? enVoices : voices
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

function splitSentences(text) {
  const clean = String(text || '')
    .replace(/[`*_#>-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!clean) return []
  const parts = clean.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [clean]
  return parts.map((s) => s.trim()).filter(Boolean)
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
        setError((prev) => prev || 'no speech heard â€” hold Space while speaking (use Google Chrome)')
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

  useEffect(
    () => () => {
      if (stopTimerRef.current) clearTimeout(stopTimerRef.current)
      recRef.current?.abort?.()
    },
    [],
  )

  return { listening, interim, error, lang, toggleLang, start, stop, supported: recognitionSupported }
}

/** Text-to-speech with persisted mute, male/female voice selector, speed control, and full-text sentence chunking. */
export function useSpeaker() {
  const [speaking, setSpeaking] = useState(false)
  const [voices, setVoices] = useState([])
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
    if (!synthesisSupported) return
    window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [])

  const say = useCallback((text, overrideOpts = {}) => {
    if (!synthesisSupported || mutedRef.current || !text) return
    const chunks = splitSentences(text)
    if (!chunks.length) return

    window.speechSynthesis.cancel()
    const targetGender = overrideOpts.gender || genderRef.current
    const targetRate = overrideOpts.rate || rateRef.current
    const available = voicesRef.current.length
      ? voicesRef.current
      : window.speechSynthesis.getVoices() || []
    const chosenVoice = pickVoice(available, targetGender)

    setSpeaking(true)
    chunks.forEach((sentence, idx) => {
      const utterance = new SpeechSynthesisUtterance(sentence)
      if (chosenVoice) utterance.voice = chosenVoice
      utterance.rate = targetRate
      utterance.pitch = targetGender === 'male' ? 0.92 : 1.08
      if (idx === chunks.length - 1) {
        utterance.onend = () => setSpeaking(false)
        utterance.onerror = () => setSpeaking(false)
      }
      window.speechSynthesis.speak(utterance)
    })
  }, [])

  const setVoiceGender = useCallback((nextGender) => {
    const clean = nextGender === 'female' ? 'female' : 'male'
    setVoiceGenderState(clean)
    genderRef.current = clean
    try {
      localStorage.setItem('nightmare.voiceGender', clean)
    } catch {
      /* ignore */
    }
  }, [])

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
    setMuted((prev) => {
      const next = !prev
      try {
        localStorage.setItem('nightmare.muted', next ? '1' : '0')
      } catch {
        /* ignore */
      }
      if (next && synthesisSupported) {
        window.speechSynthesis.cancel()
        setSpeaking(false)
      }
      return next
    })
  }, [])

  return {
    speaking,
    muted,
    voiceGender,
    rate,
    say,
    cancel,
    toggleMute,
    toggleVoiceGender,
    setVoiceGender,
    cycleRate,
    setRate,
  }
}
