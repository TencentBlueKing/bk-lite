import { describe, expect, it } from 'vitest';

import { groupTimelineByView, type TimelineLike } from '@/app/rum/sessions/lib/group-timeline';

function item(partial: TimelineLike): TimelineLike {
  return partial;
}

describe('groupTimelineByView', () => {
  it('把浏览后面的指标收到这一段，下一次浏览另起一段', () => {
    const groups = groupTimelineByView([
      item({ id: 'v1', kind: 'view', route: '/' }),
      item({ id: 'lcp', kind: 'vital', route: '/' }),
      item({ id: 'cls', kind: 'vital', route: '/' }),
      item({ id: 'a1', kind: 'action', route: '/' }),
      item({ id: 'v2', kind: 'view', route: '/checkout/' }),
      item({ id: 'e1', kind: 'error', route: '/checkout/' }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0].view?.route).toBe('/');
    expect(groups[0].vitals.map((row) => row.id)).toEqual(['lcp', 'cls']);
    expect(groups[0].rest.map((row) => row.id)).toEqual(['a1']);
    expect(groups[1].view?.route).toBe('/checkout/');
    expect(groups[1].vitals).toEqual([]);
    expect(groups[1].rest.map((row) => row.id)).toEqual(['e1']);
  });

  it('浏览之前的事件单独成一段，不并进后面的路由', () => {
    const groups = groupTimelineByView([
      item({ id: 'orphan', kind: 'error' }),
      item({ id: 'v1', kind: 'view', route: '/' }),
      item({ id: 'fcp', kind: 'vital', route: '/' }),
    ]);
    expect(groups).toHaveLength(2);
    expect(groups[0].view).toBeNull();
    expect(groups[0].rest.map((row) => row.id)).toEqual(['orphan']);
    expect(groups[1].view?.id).toBe('v1');
    expect(groups[1].vitals.map((row) => row.id)).toEqual(['fcp']);
  });
});
