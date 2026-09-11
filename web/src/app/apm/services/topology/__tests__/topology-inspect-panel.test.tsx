import { describe, expect, it } from 'vitest';

import { renderWithApmIntl } from '@/app/apm/__tests__/intl';
import TopologyInspectPanel from '../topology-inspect-panel';

describe('TopologyInspectPanel', () => {
  it('概况面板窄屏堆叠、宽屏并排，高度跟随父容器', () => {
    const { container } = renderWithApmIntl(
      <TopologyInspectPanel
        nodes={[]}
        edges={[]}
        selection={null}
        traces={[]}
        tracesLoading={false}
        startedAt="2026-08-06T01:00:00Z"
        endedAt="2026-08-06T02:00:00Z"
        serviceIds={new Map()}
        isolated={false}
        onSelectNode={() => undefined}
        onIsolate={() => undefined}
        onShowFullMap={() => undefined}
      />,
    );

    const aside = container.querySelector('aside');

    expect(aside?.classList.contains('w-full')).toBe(true);
    expect(aside?.classList.contains('lg:w-80')).toBe(true);
    expect(aside?.classList.contains('3xl:w-96')).toBe(true);
    expect(aside?.classList.contains('lg:h-full')).toBe(true);
    expect(aside?.className).not.toContain('h-[640px]');
    expect(aside?.className).not.toContain('w-[320px]');
  });
});
