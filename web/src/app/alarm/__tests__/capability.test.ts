import { describe, expect, it } from 'vitest';

import { slots } from '@/app/alarm/capability';

describe('alarm capability', () => {
  it('does not inject extra tabs into the monitor event page', () => {
    expect('monitor.event.extraTabs' in slots).toBe(false);
  });
});
