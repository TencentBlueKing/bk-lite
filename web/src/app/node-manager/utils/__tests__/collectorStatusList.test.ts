import { describe, expect, it } from 'vitest';
import { COLLECTOR_LABEL } from '../../constants/collector';
import type { TableDataItem } from '../../types';
import {
  asCollectorStatusList,
  EXECUTOR_TYPE_TAG,
  filterCollectorsForOperationType,
  groupCollectorsForOperationSelect,
  isExecutorCollector,
  listNodeHostedCollectors,
  mergeNodeCollectorStatuses
} from '../collectorConfig';

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

  it('does not treat a sidecar status object as a collector list', () => {
    expect(
      asCollectorStatusList({}).find(
        (item) => item.collector_id === 'natsexecutor_linux',
      ),
    ).toBeUndefined();
  });
});

describe('hosted executor collectors', () => {
  it('recognizes NATS and Ansible executor ids across os and arch', () => {
    expect(isExecutorCollector({ collector_id: 'natsexecutor_linux' })).toBe(
      true
    );
    expect(isExecutorCollector({ id: 'natsexecutor_linux_arm64' })).toBe(true);
    expect(isExecutorCollector({ id: 'natsexecutor_windows' })).toBe(true);
    expect(isExecutorCollector({ id: 'ansibleexecutor_linux' })).toBe(true);
    expect(isExecutorCollector({ name: 'Ansible-Executor' })).toBe(true);
    expect(isExecutorCollector({ id: 'telegraf_linux' })).toBe(false);
  });

  it('keeps executors in the hosted component list', () => {
    const record: TableDataItem = {
      id: 'node-1',
      status: {
        collectors: [
          { collector_id: 'natsexecutor_linux', status: 0 },
          { collector_id: 'telegraf_linux', status: 0 }
        ],
        collectors_install: [
          { collector_id: 'ansibleexecutor_linux', status: 11 },
          { collector_id: 'telegraf_linux', status: 11 }
        ]
      }
    };
    const hosted = listNodeHostedCollectors(record);

    expect(hosted.map((item) => item.collector_id)).toEqual([
      'natsexecutor_linux',
      'telegraf_linux',
      'ansibleexecutor_linux'
    ]);
  });

  it('merges install-only collectors without duplicating running ones', () => {
    expect(
      mergeNodeCollectorStatuses(
        [{ collector_id: 'vector_linux', status: 0 }],
        [
          { collector_id: 'vector_linux', status: 11 },
          { collector_id: 'natsexecutor_linux', status: 11 }
        ]
      ).map((item) => item.collector_id)
    ).toEqual(['vector_linux', 'natsexecutor_linux']);
  });

  it('filters operation candidates to executors even without the new tag', () => {
    const collectors = [
      { id: 'natsexecutor_linux', name: 'NATS-Executor', tags: ['linux'] },
      { id: 'telegraf_linux', name: 'Telegraf', tags: ['monitor', 'linux'] }
    ];

    expect(
      filterCollectorsForOperationType(collectors, EXECUTOR_TYPE_TAG).map(
        (item) => item.id
      )
    ).toEqual(['natsexecutor_linux']);
    expect(
      filterCollectorsForOperationType(collectors, 'monitor').map(
        (item) => item.id
      )
    ).toEqual(['telegraf_linux']);
  });

  it('groups executors as hosted components instead of controller', () => {
    const getLabelKey = (name: string) => {
      for (const key in COLLECTOR_LABEL) {
        if (COLLECTOR_LABEL[key].includes(name)) {
          return key;
        }
      }
      return undefined;
    };

    expect(
      groupCollectorsForOperationSelect(
        [
          { id: 'natsexecutor_linux', name: 'NATS-Executor' },
          { id: 'ansibleexecutor_linux', name: 'Ansible-Executor' }
        ],
        getLabelKey
      )
    ).toEqual([
      {
        label: 'Executor',
        title: 'Executor',
        options: [
          { label: 'NATS-Executor', value: 'natsexecutor_linux' },
          { label: 'Ansible-Executor', value: 'ansibleexecutor_linux' }
        ]
      }
    ]);
  });
});
