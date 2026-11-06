import { describe, expect, it } from 'vitest';

import { postgresDeadlockTone, postgresFocusQuiet } from '../overview-pane';

describe('postgres overview reading', () => {
  it('keeps a zero deadlock rate in the neutral color and alerts only above zero', () => {
    expect(postgresDeadlockTone(0, '#EF4444')).toBeUndefined();
    expect(postgresDeadlockTone(null, '#EF4444')).toBeUndefined();
    expect(postgresDeadlockTone(0.01, '#EF4444')).toBe('#EF4444');
  });

  it('quiets an all-zero focus headline and keeps weight when the window has a rise', () => {
    expect(postgresFocusQuiet(0, [0, 0, 0])).toBe(true);
    expect(postgresFocusQuiet(0, [])).toBe(true);
    expect(postgresFocusQuiet(0, [0, 1.2, 0])).toBe(false);
    expect(postgresFocusQuiet(4, [4, 4])).toBe(false);
    expect(postgresFocusQuiet(null, [0])).toBe(false);
  });
});
