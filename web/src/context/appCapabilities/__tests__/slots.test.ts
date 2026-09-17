import { describe, expect, it } from 'vitest';

import {
  collectSlotContributions,
  isHostTab,
  resolveSlot,
} from '../slots';

const GuestChart = () => null;

describe('collectSlotContributions', () => {
  it('collects matching slots and ignores missing or incomplete entries', () => {
    const contributions = collectSlotContributions(
      [
        null,
        {
          appName: 'guest',
          slots: {
            'host.extraTabs': {
              key: 'guestChart',
              labelKey: 'guest.chart',
              labelDefault: 'Guest Chart',
              component: GuestChart,
            },
          },
        },
        {
          appName: 'other',
          slots: {
            'host.extraTabs': {
              key: '',
              labelKey: 'x',
              labelDefault: 'x',
              component: GuestChart,
            },
          },
        },
      ],
      'host.extraTabs'
    );

    expect(contributions).toEqual([
      {
        appName: 'guest',
        key: 'guestChart',
        labelKey: 'guest.chart',
        labelDefault: 'Guest Chart',
        component: GuestChart,
      },
    ]);
  });
});

describe('resolveSlot', () => {
  it('finds the contribution for the active extra tab', () => {
    const contributions = collectSlotContributions(
      [
        {
          appName: 'guest',
          slots: {
            'host.extraTabs': {
              key: 'guestChart',
              labelKey: 'guest.chart',
              labelDefault: 'Guest Chart',
              component: GuestChart,
            },
          },
        },
      ],
      'host.extraTabs'
    );

    expect(resolveSlot(contributions, 'guestChart')?.appName).toBe('guest');
    expect(resolveSlot(contributions, 'missing')).toBeNull();
  });
});

describe('isHostTab', () => {
  it('treats unknown extra keys as host tabs', () => {
    expect(isHostTab('activeAlarms', ['guestChart'])).toBe(true);
    expect(isHostTab('guestChart', ['guestChart'])).toBe(false);
  });
});
