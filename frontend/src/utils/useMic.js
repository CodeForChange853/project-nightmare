import { useCallback, useEffect, useRef } from 'react'

/**
 * Opens the microphone only while you are talking, and exposes an AnalyserNode so the
 * waveform can follow real volume. If the mic can't be opened the waveform simply falls
 * back to simulated motion; speech recognition does not depend on this.
 */
export function useMic() {
  const analyserRef = useRef(null)
  const streamRef = useRef(null)
  const ctxRef = useRef(null)
  const wantedRef = useRef(false)

  const stop = useCallback(() => {
    wantedRef.current = false
    streamRef.current?.getTracks().forEach((t) => t.stop())
    ctxRef.current?.close().catch(() => {})
    streamRef.current = null
    ctxRef.current = null
    analyserRef.current = null
  }, [])

  const start = useCallback(async () => {
    if (analyserRef.current || wantedRef.current) return
    wantedRef.current = true
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!wantedRef.current) {
        stream.getTracks().forEach((t) => t.stop()) // released before the mic opened
        return
      }
      const ctx = new AudioContext()
      const source = ctx.createMediaStreamSource(stream)
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      source.connect(analyser)
      streamRef.current = stream
      ctxRef.current = ctx
      analyserRef.current = analyser
    } catch {
      wantedRef.current = false
    }
  }, [])

  useEffect(() => stop, [stop])

  return { analyserRef, start, stop }
}
