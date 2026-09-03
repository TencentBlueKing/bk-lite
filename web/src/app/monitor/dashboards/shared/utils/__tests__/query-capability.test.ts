import { describe, expect, it } from 'vitest';

import { dashboardQueryCapabilityId } from '../query-capability';
import {
  buildDynamicCapabilitySearchParams,
  buildSearchParams,
} from '../search-params';

const context = { monitorObjectId: 7, instanceId: "('host-a',)" };
const timeValues = { timeRange: [0, 3_600_000], originValue: 0 };

describe('monitor dashboard query capabilities', () => {
  it('uses a stable content id', () => {
    expect(dashboardQueryCapabilityId('up{__$labels__}')).toBe('dashboard:v1:41dd110b');
  });

  it('does not send PromQL for static dashboard queries', () => {
    const params = buildSearchParams(
      'rate(cpu_usage{__$labels__}[__$window__])',
      'percent',
      ['host-a'],
      ['instance_id'],
      timeValues,
      undefined,
      false,
      60,
      context,
    );

    expect(params.query).toBeUndefined();
    expect(params.capability_id).toBe('dashboard:v1:7aef5ba1');
    expect(params.monitor_object_id).toBe(7);
    expect(params.instance_ids).toEqual(["('host-a',)"]);
    expect(params.start).toBe(0);
    expect(params.end).toBe(3_600_000);
  });

  it('sends only registered dynamic capability parameters', () => {
    const params = buildDynamicCapabilitySearchParams({
      capabilityId: 'dashboard:dynamic:kafka:current-offset',
      capabilityParams: { dimensions: [{ topic: 'orders', partition: '0' }] },
      sourceUnit: 'counts',
      timeValues,
      context,
    });

    expect(params.query).toBeUndefined();
    expect(params.capability_id).toBe('dashboard:dynamic:kafka:current-offset');
    expect(params.capability_params).toEqual({ dimensions: [{ topic: 'orders', partition: '0' }] });
  });
});
