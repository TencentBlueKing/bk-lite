import { describe, expect, it } from 'vitest';

import {
  activateAllRuntimeWidgets,
  resolveRuntimeActivation,
  shouldCommitRuntimeStates,
} from '@/app/ops-analysis/utils/dashboardRuntimeActivation';

describe('dashboard runtime activation', () => {
  const root = { top: 100, bottom: 500 };

  it('activates the viewport plus one viewport above and below', () => {
    expect(resolveRuntimeActivation({
      root,
      widget: { top: 520, bottom: 600 },
      activationMargin: 400,
      order: 2,
    })).toEqual({
      active: true,
      priority: { cause: 1, visibility: 1, distance: 20, order: 2 },
    });

    expect(resolveRuntimeActivation({
      root,
      widget: { top: 901, bottom: 980 },
      activationMargin: 400,
      order: 3,
    }).active).toBe(false);
  });

  it('gives visible widgets priority over prefetched widgets', () => {
    const visible = resolveRuntimeActivation({
      root,
      widget: { top: 200, bottom: 300 },
      activationMargin: 400,
      order: 8,
    });
    expect(visible.priority).toEqual({
      cause: 1,
      visibility: 0,
      distance: 0,
      order: 8,
    });
  });

  it('does not commit scroll-only distance changes', () => {
    const previous = {
      a: {
        active: true,
        priority: { cause: 1, visibility: 1, distance: 20, order: 2 },
      },
    };
    const next = {
      a: {
        active: true,
        priority: { cause: 1, visibility: 1, distance: 180, order: 2 },
      },
    };
    expect(shouldCommitRuntimeStates(previous, next)).toBe(false);
  });

  it('commits when a widget enters or leaves the viewport band', () => {
    const previous = {
      a: {
        active: true,
        priority: { cause: 1, visibility: 1, distance: 20, order: 2 },
      },
    };
    const next = {
      a: {
        active: false,
        priority: { cause: 1, visibility: 1, distance: 900, order: 2 },
      },
    };
    expect(shouldCommitRuntimeStates(previous, next)).toBe(true);
  });

  it('activates every widget for report rendering', () => {
    expect(activateAllRuntimeWidgets(['a', 'b'])).toEqual({
      a: { active: true, priority: { cause: 1, visibility: 0, distance: 0, order: 0 } },
      b: { active: true, priority: { cause: 1, visibility: 0, distance: 0, order: 1 } },
    });
  });
});
