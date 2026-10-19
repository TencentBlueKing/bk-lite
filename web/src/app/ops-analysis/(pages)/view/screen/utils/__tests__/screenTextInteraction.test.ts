import { describe, expect, it } from 'vitest';
import type { ScreenTextItem } from '@/app/ops-analysis/types/screen';
import { createScreenTextItem } from '../screenItems';
import {
  persistScreenTextInteraction,
  withScreenTextInteraction,
} from '../screenTextInteraction';

const text = (): ScreenTextItem => createScreenTextItem([], {
  id: 'label',
  content: '告警关联事件来源 TOP10',
});

describe('persistScreenTextInteraction', () => {
  it('keeps a title link and drops none, data, and blank urls', () => {
    expect(persistScreenTextInteraction({
      kind: 'title',
      name: ' 查看告警 ',
      url: ' /alerts?source=$source$ ',
      openMode: 'newTab',
    })).toEqual({
      kind: 'title',
      name: '查看告警',
      url: '/alerts?source=$source$',
      openMode: 'newTab',
    });
    expect(persistScreenTextInteraction({ kind: 'none', name: '查看', url: '/ops', openMode: 'sameTab' })).toBeUndefined();
    expect(persistScreenTextInteraction({ kind: 'data', name: '查看', url: '/ops', openMode: 'sameTab' })).toBeUndefined();
    expect(persistScreenTextInteraction({ kind: 'title', name: '查看', url: '   ', openMode: 'sameTab' })).toBeUndefined();
    expect(persistScreenTextInteraction(null)).toBeUndefined();
  });

  it('removes the field when cleared and keeps it on a new text item', () => {
    const linked = withScreenTextInteraction(text(), {
      kind: 'title',
      name: '查看告警',
      url: '/alerts',
      openMode: 'sameTab',
    });
    expect(linked.interaction).toEqual({
      kind: 'title',
      name: '查看告警',
      url: '/alerts',
      openMode: 'sameTab',
    });

    const cleared = withScreenTextInteraction(linked, { kind: 'none', url: '/alerts' });
    expect(cleared.interaction).toBeUndefined();
    expect(Object.prototype.hasOwnProperty.call(cleared, 'interaction')).toBe(false);
    expect(withScreenTextInteraction(cleared, { kind: 'none' })).toBe(cleared);

    const created = createScreenTextItem([], {
      id: 'label-2',
      interaction: linked.interaction,
    });
    expect(created.interaction).toEqual(linked.interaction);
  });
});
