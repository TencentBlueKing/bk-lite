import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { MetricSeries } from '../../../common/simple-dashboard-core';
import { POSTGRESQL_DASHBOARD_CONFIG } from '../../config';
import {
  POSTGRES_RECOVERY_QUERY,
  POSTGRES_REPLICATION_SLOTS_QUERY,
  POSTGRES_STREAMING_REPLICAS_QUERY
} from '../../queries';
import { POSTGRES_CATEGORY_METRIC_NAMES } from '../metrics';
import ReplicationPane from '../replication-pane';
import {
  postgresReplicationDimmed,
  postgresReplicationTabMode,
  readPostgresReplication,
  type PostgresReplicationMetricName
} from '../replication';
import type { PostgresMetricMap } from '../series';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false
    })
  });
});

const series = (
  value: number | null,
  loadState: MetricSeries['loadState'] = 'success'
): MetricSeries => ({
  name: 'replication',
  display_name: 'replication',
  description: '',
  unit: 'counts',
  query: '',
  color: '#2563EB',
  loadState,
  viewData: value == null ? [] : [{ time: 1, value1: value }]
});

const mapOf = (values: Partial<Record<PostgresReplicationMetricName, number | null>>): PostgresMetricMap => {
  const map: PostgresMetricMap = {};
  (Object.keys(values) as PostgresReplicationMetricName[]).forEach((name) => {
    map[name] = series(values[name] ?? null);
  });
  return map;
};

const card = (key: string) => document.querySelector(`[data-postgres-replication-card="${key}"]`);

describe('postgres replication load', () => {
  it('keeps a primary with replicas and slots out of the empty state, including recovery 0', () => {
    const model = readPostgresReplication(mapOf({
      postgresql_recovery_in_recovery: 0,
      postgresql_replication_streaming_replicas: 2,
      postgresql_replication_replication_slots: 2
    }), new Set());
    expect(model.load).toBe('ready');
    expect(postgresReplicationDimmed(model.load)).toBe(false);
    expect(postgresReplicationTabMode(model.load)).toBe('ready');
    expect(model.roleText).toBe('主库');
    expect(model.streamingText).toBe('2');
    expect(model.slotsText).toBe('2');
    expect(model.note).toBe('none');
  });

  it('shows sampled zeros instead of 未采集, and says a primary has no downstream', () => {
    const model = readPostgresReplication(mapOf({
      postgresql_recovery_in_recovery: 0,
      postgresql_replication_streaming_replicas: 0,
      postgresql_replication_replication_slots: 0
    }), new Set());
    expect(model.load).toBe('ready');
    expect(postgresReplicationDimmed(model.load)).toBe(false);
    expect(model.streaming).toBe(0);
    expect(model.slots).toBe(0);
    expect(model.streamingText).toBe('0');
    expect(model.slotsText).toBe('0');
    expect(model.note).toBe('primary_no_downstream');
  });

  it('does not call a standby with zero peers unconfigured', () => {
    const model = readPostgresReplication(mapOf({
      postgresql_recovery_in_recovery: 1,
      postgresql_replication_streaming_replicas: 0,
      postgresql_replication_replication_slots: 0
    }), new Set());
    expect(model.roleText).toBe('备库');
    expect(model.note).toBe('none');
    expect(model.load).toBe('ready');
  });

  it('says replication is not configured when both counts are sampled zeros and the role is unknown', () => {
    const model = readPostgresReplication(mapOf({
      postgresql_replication_streaming_replicas: 0,
      postgresql_replication_replication_slots: 0
    }), new Set());
    expect(model.load).toBe('ready');
    expect(model.roleText).toBe('—');
    expect(model.note).toBe('unconfigured');
  });

  it('does not invent a zero for a metric that has no sample', () => {
    const model = readPostgresReplication(mapOf({
      postgresql_replication_streaming_replicas: 0
    }), new Set());
    expect(model.load).toBe('ready');
    expect(model.streamingText).toBe('0');
    expect(model.slots).toBeNull();
    expect(model.slotsText).toBe('—');
    expect(model.roleText).toBe('—');
    expect(model.note).toBe('none');
  });

  it('treats a fully empty window as 未采集, including failed queries', () => {
    expect(readPostgresReplication({}, new Set()).load).toBe('not_collected');
    const failed = readPostgresReplication({
      postgresql_recovery_in_recovery: series(null, 'error'),
      postgresql_replication_streaming_replicas: series(null),
      postgresql_replication_replication_slots: series(null, 'error')
    }, new Set());
    expect(failed.load).toBe('not_collected');
    expect(postgresReplicationDimmed(failed.load)).toBe(true);
    expect(postgresReplicationTabMode(failed.load)).toBe('empty');
  });

  it('stays loading while the replication queries are still out', () => {
    const pending = new Set(['postgresql_replication_streaming_replicas']);
    const model = readPostgresReplication({}, pending);
    expect(model.load).toBe('loading');
    expect(postgresReplicationDimmed(model.load)).toBe(false);
    expect(readPostgresReplication({}, new Set(), true).load).toBe('loading');
  });

  it('wires the three plugin queries into the category fetch list', () => {
    const queries: Record<PostgresReplicationMetricName, string> = {
      postgresql_recovery_in_recovery: POSTGRES_RECOVERY_QUERY,
      postgresql_replication_streaming_replicas: POSTGRES_STREAMING_REPLICAS_QUERY,
      postgresql_replication_replication_slots: POSTGRES_REPLICATION_SLOTS_QUERY
    };
    (Object.keys(queries) as PostgresReplicationMetricName[]).forEach((name) => {
      expect(POSTGRES_CATEGORY_METRIC_NAMES).toContain(name);
      expect(POSTGRESQL_DASHBOARD_CONFIG.metrics.find((item) => item.name === name)?.query).toBe(queries[name]);
    });
  });
});

describe('postgres replication pane', () => {
  it('renders the HA primary counts and no lag chart', () => {
    render(
      <ReplicationPane
        metricMap={mapOf({
          postgresql_recovery_in_recovery: 0,
          postgresql_replication_streaming_replicas: 2,
          postgresql_replication_replication_slots: 2
        })}
        pendingMetricNames={new Set()}
      />
    );
    expect(screen.getByText('主库')).toBeTruthy();
    expect(card('streaming')?.textContent).toContain('2');
    expect(card('slots')?.textContent).toContain('2');
    expect(card('streaming')?.getAttribute('data-postgres-replication-value')).toBe('2');
    expect(screen.queryByText('复制状态未采集')).toBeNull();
    expect(screen.queryByText('当前未配置复制')).toBeNull();
    expect(screen.queryByText('主库 · 暂无下游')).toBeNull();
    expect(screen.getByText('本环境未采复制延迟/积压，不展示趋势。')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-trends="none"]')).toBeTruthy();
    expect(document.querySelector('canvas')).toBeNull();
  });

  it('renders sampled zeros with the no-downstream note', () => {
    render(
      <ReplicationPane
        metricMap={mapOf({
          postgresql_recovery_in_recovery: 0,
          postgresql_replication_streaming_replicas: 0,
          postgresql_replication_replication_slots: 0
        })}
        pendingMetricNames={new Set()}
      />
    );
    expect(card('streaming')?.getAttribute('data-postgres-replication-value')).toBe('0');
    expect(card('slots')?.getAttribute('data-postgres-replication-value')).toBe('0');
    expect(card('streaming')?.textContent).toContain('0');
    expect(card('slots')?.textContent).toContain('0');
    expect(screen.getByText('主库 · 暂无下游')).toBeTruthy();
    expect(screen.getByText('本环境未采复制延迟/积压，不展示趋势。')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-trends="none"]')).toBeTruthy();
    expect(document.querySelector('canvas')).toBeNull();
    expect(screen.queryByText('复制状态未采集')).toBeNull();
  });

  it('uses the honest empty state only when nothing was sampled', () => {
    const onOpenCollection = vi.fn();
    render(
      <ReplicationPane
        metricMap={{}}
        pendingMetricNames={new Set()}
        onOpenCollection={onOpenCollection}
      />
    );
    expect(screen.getByText('复制状态未采集')).toBeTruthy();
    expect(screen.getByText('本窗口未见复制/恢复相关采点；确认采集任务在跑且至少一个周期已上报。')).toBeTruthy();
    expect(screen.queryByText('去开启复制')).toBeNull();
    expect(document.querySelector('[data-postgres-replication-card]')).toBeNull();
    expect(screen.queryByText('本环境未采复制延迟/积压，不展示趋势。')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '查看采集配置' }));
    expect(onOpenCollection).toHaveBeenCalledOnce();
  });
});
