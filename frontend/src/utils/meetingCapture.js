// Separate from command recognition: these callbacks only update meeting captions.
export class MeetingCapture {
  constructor({ onFinal, onInterim, onState, onError }, env = globalThis) {
    Object.assign(this, { onFinal, onInterim, onState, onError, env })
    this.streams = []
    this.generation = 0
  }

  stop() {
    this.generation++
    this.active = false
    clearTimeout(this.timer)
    if (this.rec) {
      this.rec.onend = null
      this.rec.onresult = null
      this.rec.onerror = null
      this.rec.abort()
      this.rec = null
    }
    for (const stream of this.streams) for (const track of stream.getTracks()) track.stop()
    this.streams = []
    this.context?.close().catch(() => {})
    this.context = null
    this.onInterim('')
    this.onState('stopped')
  }

  async start(source) {
    this.stop()
    const generation = this.generation
    const current = () => generation === this.generation
    const { env } = this
    const Recognition = env.SpeechRecognition || env.webkitSpeechRecognition
    if (!Recognition) return this.onError('Speech recognition is unavailable. Open Nightmare in desktop Chrome.')
    this.onState('starting')
    try {
      let audioTrack
      if (source !== 'mic') {
        // Older implementations silently ignore start(track) and listen to the mic.
        const version = /(?:Chrome|Chromium)\/(\d+)/.exec(env.navigator.userAgent)
        if (!version || Number(version[1]) < 135 || /Android|Mobile/.test(env.navigator.userAgent)) {
          throw new Error('PC audio requires desktop Chrome 135 or newer. Use microphone mode in this browser.')
        }
        const display = await env.navigator.mediaDevices.getDisplayMedia({
          video: true, audio: true, systemAudio: 'include',
        })
        if (!current()) { display.getTracks().forEach((t) => t.stop()); return }
        this.streams.push(display)
        audioTrack = display.getAudioTracks()[0]
        if (!audioTrack) throw new Error('No PC audio was shared. Select a meeting tab or screen and enable Share audio.')
        for (const track of display.getTracks()) track.onended = () => { if (current()) this.stop() }
        if (source === 'both') {
          const mic = await env.navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true }, video: false })
          if (!current()) { mic.getTracks().forEach((t) => t.stop()); return }
          this.streams.push(mic)
          for (const track of mic.getTracks()) track.onended = () => { if (current()) this.stop() }
          const context = new env.AudioContext()
          this.context = context
          await context.resume()
          if (!current()) return
          const destination = context.createMediaStreamDestination()
          context.createMediaStreamSource(new env.MediaStream([audioTrack])).connect(destination)
          context.createMediaStreamSource(mic).connect(destination)
          this.streams.push(destination.stream)
          audioTrack = destination.stream.getAudioTracks()[0]
        }
      }
      if (!current()) return
      this.active = true
      const listen = () => {
        if (!current() || !this.active) return
        const rec = new Recognition()
        this.rec = rec
        rec.lang = 'zh-CN'
        rec.continuous = true
        rec.interimResults = true
        rec.maxAlternatives = 1
        rec.onstart = () => { if (current()) this.onState('listening') }
        rec.onresult = (event) => {
          if (!current()) return
          let interim = ''
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const result = event.results[i]
            if (result.isFinal) {
              const text = result[0].transcript.trim()
              if (text) this.onFinal(text)
            } else interim += result[0].transcript
          }
          this.onInterim(interim)
        }
        rec.onerror = (event) => {
          if (!current() || event.error === 'no-speech') return
          this.stop()
          this.onError(`Speech recognition: ${event.error}. Check microphone permission, internet, and browser support.`)
        }
        rec.onend = () => {
          if (!current() || !this.active) return
          this.onInterim('')
          this.onState('reconnecting')
          this.timer = setTimeout(() => {
            try { listen() } catch (err) { this.stop(); this.onError(err.message) }
          }, 500)
        }
        if (audioTrack) rec.start(audioTrack)
        else rec.start()
      }
      listen()
    } catch (err) {
      if (!current()) return
      this.stop()
      this.onError(err.message || String(err))
    }
  }
}
