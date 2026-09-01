import { describe, expect, it } from 'vitest';

import { contextUsagePercent, formatContextTokens, parseLlmContextUsage, parseLlmContextUsageFromEnvelope } from '../llmContextUsage';

const SECRET = 'sk-usage-ring-PROMPT-SENTINEL';

describe('parseLlmContextUsage', () => {
  it('keeps bounded counts and drops unknown fields and content', () => {
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
    expect(usage).toEqual({
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
    expect(JSON.stringify(usage)).not.toContain(SECRET);
  });

  it('rejects snapshots without a working budget', () => {
    expect(parseLlmContextUsage({ packet_tokens: 12, input_working_tokens: 0 })).toBeNull();
    expect(parseLlmContextUsage(null)).toBeNull();
  });

  it('reads session envelope snapshots without leaking history text', () => {
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
    expect(usage?.packetTokens).toBe(1200);
    expect(JSON.stringify(usage)).not.toContain(SECRET);
    expect(parseLlmContextUsageFromEnvelope([{ id: 1 }])).toBeNull();
  });

  it('formats token counts the way the ring caption does', () => {
    expect(formatContextTokens(6800)).toBe('6.8K');
    expect(formatContextTokens(186000)).toBe('186K');
    expect(formatContextTokens(1_000_000)).toBe('1M');
  });

  it('caps the ring percent at 100 against the input working budget', () => {
    expect(
      contextUsagePercent({
        packetTokens: 9100,
        inputWorkingTokens: 6800,
        windowTokens: 8000,
        compactionThresholdTokens: 5100,
        compacted: false,
        segments: [],
      })
    ).toBe(100);
    expect(
      contextUsagePercent({
        packetTokens: 3400,
        inputWorkingTokens: 6800,
        windowTokens: 8000,
        compactionThresholdTokens: 5100,
        compacted: false,
        segments: [],
      })
    ).toBe(50);
  });
});
