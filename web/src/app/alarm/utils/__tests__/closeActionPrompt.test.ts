import { describe, expect, it } from 'vitest';
import { shouldPromptActionOnClose } from '../closeActionPrompt';

const baseRule = {
  is_active: true,
  auto_execute: false,
  trigger_events: ['created', 'closed'],
  team: [1],
};

describe('shouldPromptActionOnClose', () => {
  it('prompts when auto execute is off and closed is checked', () => {
    expect(shouldPromptActionOnClose(baseRule, { team: [1] })).toBe(true);
  });

  it('does not prompt when auto execute is on', () => {
    expect(
      shouldPromptActionOnClose({ ...baseRule, auto_execute: true }, { team: [1] })
    ).toBe(false);
  });

  it('does not prompt when auto execute is omitted', () => {
    expect(
      shouldPromptActionOnClose(
        {
          is_active: true,
          trigger_events: ['created', 'closed'],
          team: [1],
        },
        { team: [1] }
      )
    ).toBe(false);
  });

  it('does not prompt when closed is not a trigger event', () => {
    expect(
      shouldPromptActionOnClose(
        { ...baseRule, trigger_events: ['created'] },
        { team: [1] }
      )
    ).toBe(false);
  });

  it('does not prompt for inactive rules', () => {
    expect(
      shouldPromptActionOnClose({ ...baseRule, is_active: false }, { team: [1] })
    ).toBe(false);
  });

  it('does not prompt when the rule team does not overlap the alert', () => {
    expect(shouldPromptActionOnClose(baseRule, { team: [9] })).toBe(false);
  });

  it('prompts for a global rule with empty team', () => {
    expect(shouldPromptActionOnClose({ ...baseRule, team: [] }, { team: [9] })).toBe(
      true
    );
  });
});
