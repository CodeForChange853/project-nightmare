// Show the word at a browser speech boundary before its audio finishes.
export function nextWordEnd(text, index = 0) {
  const start = Math.max(0, Math.min(text.length, Number(index) || 0))
  const word = /^\s*\S+/.exec(text.slice(start))
  return word ? start + word[0].length : text.length
}

// Keep captions to a short phrase, preserving offsets into the spoken text.
export function lyricLines(text, maxChars = 62, maxWords = 10) {
  const words = [...String(text).matchAll(/\S+/g)]
  const lines = []
  let start = 0
  for (let i = 0; i < words.length; i++) {
    const word = words[i]
    const end = word.index + word[0].length
    const next = words[i + 1]
    const sentenceEnd = /[.!?]["'\u201d\u2019)]*$/.test(word[0])
    if (!next || sentenceEnd || i - start + 1 >= maxWords || next.index + next[0].length - words[start].index > maxChars) {
      lines.push({ start: words[start].index, end, text: text.slice(words[start].index, end), words: i - start + 1 })
      start = i + 1
    }
  }
  return lines
}
