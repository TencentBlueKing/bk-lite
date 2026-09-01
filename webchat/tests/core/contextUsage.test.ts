import assert from 'node:assert/strict';
import test from 'node:test';

import {
  contextUsagePercent,
  formatContextTokens,
  parseLlmContextUsage,
  parseLlmContextUsageFromEnvelope,
} from '../../packages/webchat-core/src/contextUsage';

const SECRET = 'sk-usage-ring-PROMPT-SENTINEL';

test('parseLlmContextUsage keeps bounded counts and drops unknown fields', () => {
  const usage = parseLlmContextUsage({
    packet_tokens: 9100,
    input_working_tokens: 6800,
    window_tokens: 8000,
    compaction_threshold_tokens: 5100,
    compacted: true,
    prompt: SECRET,
    segments: [
      { id: 'system', tokens: 400 },
      { id: 'conversation', tokens: 8700, content: SECRET },
      { id: 'unknown', tokens: 12 },
      { id: 'tools', tokens: 0 },
    ],
  });
  assert.deepEqual(usage, {
    packetTokens: 9100,
    inputWorkingTokens: 6800,
    windowTokens: 8000,
    compactionThresholdTokens: 5100,
    compacted: true,
    segments: [
      { id: 'system', tokens: 400 },
      { id: 'conversation', tokens: 8700 },
    ],
  });
  assert.equal(JSON.stringify(usage).includes(SECRET), false);
});

test('parseLlmContextUsage rejects snapshots without a working budget', () => {
  assert.equal(parseLlmContextUsage({ packet_tokens: 12, input_working_tokens: 0 }), null);
  assert.equal(parseLlmContextUsage(null), null);
});

test('parseLlmContextUsageFromEnvelope reads session payload without leaking history text', () => {
  const usage = parseLlmContextUsageFromEnvelope({
    messages: [{ conversation_content: SECRET }],
    llm_context_usage: {
      packet_tokens: 1200,
      input_working_tokens: 6800,
      window_tokens: 8000,
      compaction_threshold_tokens: 5100,
      compacted: false,
      segments: [{ id: 'conversation', tokens: 1200, content: SECRET }],
    },
  });
  assert.equal(usage?.packetTokens, 1200);
  assert.equal(JSON.stringify(usage).includes(SECRET), false);
  assert.equal(parseLlmContextUsageFromEnvelope([{ id: 1 }]), null);
});

test('formatContextTokens and percent match the ring caption', () => {
  assert.equal(formatContextTokens(6800), '6.8K');
  assert.equal(
    contextUsagePercent({
      packetTokens: 3400,
      inputWorkingTokens: 6800,
      windowTokens: 8000,
      compactionThresholdTokens: 5100,
      compacted: false,
      segments: [],
    }),
    50
  );
});
