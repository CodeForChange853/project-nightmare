// npm test  (Node's built-in runner, no extra packages)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { mergeTranscripts } from '../src/utils/transcript.js'

test('Android: growing guesses collapse to one phrase (from the 2026-10-20 activity log)', () => {
  assert.equal(
    mergeTranscripts(['how', 'how many', 'how many', 'how many', 'how many', 'how many', 'how many projects i have']),
    'how many projects i have',
  )
  assert.equal(
    mergeTranscripts([
      'looks', 'looks like', 'looks like', 'looks like my', 'looks like my', 'looks like my text',
      'looks like my text', 'looks like my text is', 'looks like my text is repetitive',
    ]),
    'looks like my text is repetitive',
  )
})

test('Android: a re-guessed last word replaces the earlier guess', () => {
  assert.equal(mergeTranscripts(['how mini', 'how many projects']), 'how many projects')
})

test('a shorter echo of the last piece is dropped', () => {
  assert.equal(mergeTranscripts(['progress of bims', 'progress of']), 'progress of bims')
})

test('desktop: consecutive pieces are kept in order', () => {
  assert.equal(mergeTranscripts(['how many', ' projects do I have']), 'how many projects do I have')
  assert.equal(mergeTranscripts(['hello', 'world']), 'hello world')
  assert.equal(mergeTranscripts(['open youtube', 'and search lofi']), 'open youtube and search lofi')
  assert.equal(mergeTranscripts(['remind me to', 'remind the class']), 'remind me to remind the class')
})

test('empty input', () => {
  assert.equal(mergeTranscripts([]), '')
  assert.equal(mergeTranscripts(['  ', 'hi']), 'hi')
})
