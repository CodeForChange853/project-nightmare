import assert from 'node:assert/strict'
import { test } from 'node:test'
import { MeetingCapture } from '../src/utils/meetingCapture.js'
import { pickVoice } from '../src/utils/useSpeech.js'

function setup(extra = {}) {
  const final = [], interim = [], states = [], errors = [], calls = []
  class Recognition {
    constructor() { calls.push(this) }
    start(track) { this.track = track; this.onstart?.() }
    abort() { this.aborted = true }
  }
  const env = { SpeechRecognition: Recognition, navigator: { userAgent: 'Chrome/140.0', mediaDevices: {} }, ...extra }
  const capture = new MeetingCapture({ onFinal: (v) => final.push(v), onInterim: (v) => interim.push(v), onState: (v) => states.push(v), onError: (v) => errors.push(v) }, env)
  return { capture, final, interim, states, errors, calls, env }
}

test('meeting results emit final utterances once and keep interim speech separate', async () => {
  const s = setup()
  await s.capture.start('mic')
  const final = Object.assign([{ transcript: '你好' }], { isFinal: true })
  const interim = Object.assign([{ transcript: '我们' }], { isFinal: false })
  s.calls[0].onresult({ resultIndex: 0, results: [final, interim] })
  s.calls[0].onresult({ resultIndex: 1, results: [final, interim] })
  assert.deepEqual(s.final, ['你好'])
  assert.equal(s.interim.at(-1), '我们')
  assert.equal(s.calls[0].lang, 'zh-CN')
  s.capture.stop()
  assert.equal(s.calls[0].aborted, true)
})

test('PC capture passes shared audio to recognition and stops all tracks', async () => {
  const s = setup()
  const audio = { kind: 'audio', stopped: false, stop() { this.stopped = true } }
  const video = { kind: 'video', stop() { this.stopped = true } }
  s.env.navigator.mediaDevices.getDisplayMedia = async () => ({ getTracks: () => [video, audio], getAudioTracks: () => [audio] })
  await s.capture.start('pc')
  assert.equal(s.calls[0].track, audio)
  video.onended()
  assert.equal(audio.stopped, true)
  assert.equal(video.stopped, true)
  assert.equal(s.states.at(-1), 'stopped')
})

test('missing shared audio fails without silently listening to microphone', async () => {
  const s = setup()
  let stopped = false
  s.env.navigator.mediaDevices.getDisplayMedia = async () => ({ getTracks: () => [{ stop() { stopped = true } }], getAudioTracks: () => [] })
  await s.capture.start('pc')
  assert.match(s.errors[0], /No PC audio/)
  assert.equal(s.calls.length, 0)
  assert.equal(stopped, true)
})

test('mixed input connects shared audio and microphone to the recognition track without speaker feedback', async () => {
  const s = setup()
  const stopped = [], connected = []
  const track = (id) => ({ id, kind: 'audio', stop() { stopped.push(id) } })
  const stream = (audio) => ({ getTracks: () => [audio], getAudioTracks: () => [audio] })
  const pc = track('pc'), mic = track('mic'), mixed = track('mixed')
  s.env.navigator.mediaDevices.getDisplayMedia = async () => stream(pc)
  s.env.navigator.mediaDevices.getUserMedia = async () => stream(mic)
  s.env.MediaStream = class { constructor(tracks) { this.tracks = tracks } }
  let closed = false
  const destination = { stream: stream(mixed) }
  s.env.AudioContext = class {
    async resume() {}
    createMediaStreamDestination() { return destination }
    createMediaStreamSource(input) { return { connect(output) { connected.push([input, output]) } } }
    async close() { closed = true }
  }
  await s.capture.start('both')
  assert.equal(s.calls[0].track, mixed)
  assert.equal(connected.length, 2)
  assert.ok(connected.every(([, output]) => output === destination))
  s.capture.stop()
  assert.deepEqual(stopped.sort(), ['mic', 'mixed', 'pc'])
  assert.equal(closed, true)
})

test('closing while the audio picker is open disposes the returned stream', async () => {
  const s = setup()
  let resolve, stopped = false
  s.env.navigator.mediaDevices.getDisplayMedia = () => new Promise((r) => { resolve = r })
  const started = s.capture.start('pc')
  s.capture.stop()
  resolve({ getTracks: () => [{ stop() { stopped = true } }] })
  await started
  assert.equal(stopped, true)
  assert.equal(s.calls.length, 0)
})

test('recognition permission error stops capture instead of repeatedly requesting access', async () => {
  const s = setup()
  await s.capture.start('mic')
  s.calls[0].onerror({ error: 'not-allowed' })
  assert.equal(s.capture.active, false)
  assert.equal(s.calls[0].aborted, true)
  assert.match(s.errors[0], /not-allowed/)
})

test('voice selection prefers natural voices and honors explicit choices with fallback', () => {
  const voices = [
    { name: 'Microsoft David', lang: 'en-US', voiceURI: 'basic' },
    { name: 'Microsoft Guy Online (Natural)', lang: 'en-US', voiceURI: 'natural' },
    { name: 'Google US English', lang: 'en-US', voiceURI: 'google' },
  ]
  assert.equal(pickVoice(voices, 'male').voiceURI, 'natural')
  assert.equal(pickVoice(voices, 'male', 'google').voiceURI, 'google')
  assert.equal(pickVoice(voices, 'male', 'missing').voiceURI, 'natural')
  assert.equal(pickVoice([], 'male'), null)
})
