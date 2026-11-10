import assert from 'node:assert/strict'
import { test } from 'node:test'
import { lyricLines, nextWordEnd } from '../src/utils/speechProgress.js'

test('caption boundaries reveal the current word, including punctuation and Unicode', () => {
  const text = 'Hello, 世界! Next sentence.'
  assert.equal(text.slice(0, nextWordEnd(text, 0)), 'Hello,')
  assert.equal(text.slice(0, nextWordEnd(text, 7)), 'Hello, 世界!')
  assert.equal(text.slice(0, nextWordEnd(text, 11)), 'Hello, 世界! Next')
  assert.equal(text.slice(0, nextWordEnd(text, 16)), text)
})

test('lyric phrases keep exact speech offsets and split long lists into readable lines', () => {
  const text = 'You have 17 projects on your Desktop: bims, citizengraph, other, and more. Ready for the next task?'
  const lines = lyricLines(text)
  assert.ok(lines.length >= 3)
  for (const line of lines) {
    assert.equal(text.slice(line.start, line.end), line.text)
    assert.ok(line.words <= 10)
    assert.ok(line.text.length <= 62)
  }
  assert.equal(lines.map((line) => line.text).join(' '), text)
  assert.equal(lines.at(-1).text, 'Ready for the next task?')
  assert.deepEqual(lyricLines(''), [])
})

test('caption fallback advances through whitespace and safely clamps missing boundaries', () => {
  const text = 'One   two\nthree'
  let index = nextWordEnd(text)
  assert.equal(index, 3)
  index = nextWordEnd(text, index)
  assert.equal(text.slice(0, index), 'One   two')
  assert.equal(nextWordEnd(text, index), text.length)
  assert.equal(nextWordEnd(text, 1000), text.length)
  assert.equal(nextWordEnd('', 0), 0)
  assert.equal(nextWordEnd(text, -100), 3)
})
