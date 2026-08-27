import { beforeAll, describe, expect, it, vi } from 'vitest';

const stubComponent = () => null;

vi.mock('@/app/ops-analysis/components/widgets/comPie', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comLine', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comBar', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comTable', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comSingle', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comTopN', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comGauge', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/eventTable/eventTable', () => ({
  default: stubComponent,
}));
vi.mock('@/app/ops-analysis/components/widgets/networkStatusTopology', () => ({
  default: stubComponent,
}));
vi.mock('@/app/ops-analysis/components/widgets/room3D', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comMultiValue', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comEventTimeline', () => ({
  default: stubComponent,
}));
vi.mock('@/app/ops-analysis/components/widgets/comCardList', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/comRadar', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/ops-analysis-widgets/text-panel', () => ({
  default: stubComponent,
}));
vi.mock('@/app/ops-analysis/components/widgets/topologyMap', () => ({ default: stubComponent }));
vi.mock('@/app/ops-analysis/components/widgets/application3D', () => ({ default: stubComponent }));

describe('scene widget runtime surface enforcement', () => {
  let getWidgetComponent: typeof import('../widgetRegistry').getWidgetComponent;

  beforeAll(async () => {
    ({ getWidgetComponent } = await import('../widgetRegistry'));
  });

  it('mounts application3D only on screen', () => {
    expect(getWidgetComponent('application3D', 'screen')).not.toBeNull();
    expect(getWidgetComponent('application3D', 'dashboard')).toBeNull();
    expect(getWidgetComponent('application3D', 'report')).toBeNull();
  });

  it('keeps networkStatusTopology on dashboard and screen, not report', () => {
    expect(getWidgetComponent('networkStatusTopology', 'dashboard')).not.toBeNull();
    expect(getWidgetComponent('networkStatusTopology', 'screen')).not.toBeNull();
    expect(getWidgetComponent('networkStatusTopology', 'report')).toBeNull();
  });

  it('does not gate ordinary chart types by surface', () => {
    expect(getWidgetComponent('line', 'dashboard')).not.toBeNull();
    expect(getWidgetComponent('line', 'screen')).not.toBeNull();
    expect(getWidgetComponent('line', 'report')).not.toBeNull();
    expect(getWidgetComponent('room3D', 'screen')).not.toBeNull();
  });
});
