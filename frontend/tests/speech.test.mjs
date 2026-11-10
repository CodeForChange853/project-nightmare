import assert from 'node:assert/strict'
import { test } from 'node:test'
import { splitSentences, ProgressiveSentenceChunker } from '../src/utils/useSpeech.js'

test('splitSentences: separates multiple sentences cleanly on /[.!?]/', () => {
  const text = 'Hello world! This is test number two. Is everything working as expected? Yes it is.'
  const parts = splitSentences(text)
  assert.deepEqual(parts, [
    'Hello world!',
    'This is test number two.',
    'Is everything working as expected?',
    'Yes it is.',
  ])
})

test('splitSentences: handles single sentence and stripped markdown', () => {
  const text = '`Single` *sentence* without terminal punctuation'
  const parts = splitSentences(text)
  assert.deepEqual(parts, ['Single sentence without terminal punctuation'])
})

test('ProgressiveSentenceChunker: emits first sentence immediately when delimiter is received', () => {
  const emitted = []
  const chunker = new ProgressiveSentenceChunker((sentence) => {
    emitted.push(sentence)
  })

  // Push incomplete first sentence
  chunker.push('The preliminary research')
  assert.equal(emitted.length, 0)

  // Push end of first sentence with trailing space
  chunker.push(' demonstrates high accuracy. ')
  assert.equal(emitted.length, 1)
  assert.equal(emitted[0], 'The preliminary research demonstrates high accuracy.')

  // Push second sentence in multiple parts
  chunker.push('Next step is ')
  assert.equal(emitted.length, 1)
  chunker.push('validating the AST! And ')
  assert.equal(emitted.length, 2)
  assert.equal(emitted[1], 'Next step is validating the AST!')

  // Flush remaining partial text
  chunker.flush()
  assert.equal(emitted.length, 3)
  assert.equal(emitted[2], 'And')
})

test('ProgressiveSentenceChunker: handles multiple complete sentences in one chunk', () => {
  const emitted = []
  const chunker = new ProgressiveSentenceChunker((s) => emitted.push(s))

  chunker.push('Sentence one. Sentence two? Sentence three! Trailing without delimiter')
  assert.deepEqual(emitted, [
    'Sentence one.',
    'Sentence two?',
    'Sentence three!',
  ])

  chunker.flush()
  assert.deepEqual(emitted, [
    'Sentence one.',
    'Sentence two?',
    'Sentence three!',
    'Trailing without delimiter',
  ])
})
