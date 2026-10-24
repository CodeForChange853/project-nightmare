// Turning SpeechRecognition results into one transcript.
//
// Desktop Chrome gives consecutive pieces: ["how many", "projects do I have"].
// Android Chrome (continuous mode) gives every growing guess as its own result:
// ["how", "how many", "how many projects"], so joining them all repeats words.
// A result that repeats the previous piece (its last word may be re-guessed, "how mini" ->
// "how many projects") replaces that piece; a shorter echo of it is dropped.

const words = (text) => text.toLowerCase().match(/[\p{L}\p{N}']+/gu) ?? []

function startsWithWords(longer, shorter, count) {
  for (let i = 0; i < count; i++) if (longer[i] !== shorter[i]) return false
  return true
}

export function mergeTranscripts(parts) {
  const pieces = []
  for (const raw of parts) {
    const part = (raw ?? '').trim()
    const next = words(part)
    if (!next.length) continue
    const last = pieces.length ? words(pieces[pieces.length - 1]) : []
    if (last.length && next.length <= last.length && startsWithWords(last, next, next.length)) continue
    // all but the last word must match (and at least one), so separate phrases never merge
    const must = Math.max(1, last.length - 1)
    if (last.length && next.length >= last.length && startsWithWords(next, last, must)) {
      pieces[pieces.length - 1] = part
    } else {
      pieces.push(part)
    }
  }
  return pieces.join(' ')
}
