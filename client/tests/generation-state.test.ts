import assert from 'node:assert/strict';
import test from 'node:test';

import {
  isChatGenerating,
  setChatGenerating,
} from '../src/lib/generation-state.ts';

test('switching the active chat does not clear another chat generation', () => {
  const state = setChatGenerating({}, 'chat-a', true);

  assert.equal(isChatGenerating(state, 'chat-b'), false);
  assert.equal(isChatGenerating(state, 'chat-a'), true);
});

test('a terminal event clears only its originating chat', () => {
  const bothGenerating = setChatGenerating(
    setChatGenerating({}, 'chat-a', true),
    'chat-b',
    true,
  );
  const chatAFinished = setChatGenerating(bothGenerating, 'chat-a', false);

  assert.equal(isChatGenerating(chatAFinished, 'chat-a'), false);
  assert.equal(isChatGenerating(chatAFinished, 'chat-b'), true);
});

test('clearing an idle chat preserves the existing state object', () => {
  const state = setChatGenerating({}, 'chat-a', true);
  assert.equal(setChatGenerating(state, 'chat-b', false), state);
});
