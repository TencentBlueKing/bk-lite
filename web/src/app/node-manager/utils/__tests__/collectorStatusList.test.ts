import { describe, expect, it } from 'vitest';
import { asCollectorStatusList } from '../collectorConfig';

describe('asCollectorStatusList', () => {
  it('keeps a collector array', () => {
    const collectors = [{ collector_id: 'natsexecutor_linux' }];
    expect(asCollectorStatusList(collectors)).toBe(collectors);
  });

  it('turns missing or non-array sidecar status into an empty list', () => {
    expect(asCollectorStatusList(undefined)).toEqual([]);
    expect(asCollectorStatusList(null)).toEqual([]);
    expect(asCollectorStatusList({})).toEqual([]);
    expect(asCollectorStatusList('notalist')).toEqual([]);
  });

  it('lets controller column find NATS executor when sidecar status is an object', () => {
    expect(
      asCollectorStatusList({}).find(
        (item) => item.collector_id === 'natsexecutor_linux',
      ),
    ).toBeUndefined();
  });
});
