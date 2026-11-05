import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/app/monitor/dashboards/shared/widgets/useECharts', () => ({
  useECharts: () => ({
    containerRef: () => undefined,
    getInstance: () => null
  })
}));

import type { MetricSeries } from '../../../common/simple-dashboard-core';
import { readableAxisBounds, seriesSitsOnAxisFloor } from '../../../host/layered/thin-time-series';
import { POSTGRESQL_DASHBOARD_CONFIG } from '../../config';
import {
  POSTGRES_FLUSH_LAG_QUERY,
  POSTGRES_RECOVERY_QUERY,
  POSTGRES_REPLAY_LAG_QUERY,
  POSTGRES_REPLICATION_SLOTS_QUERY,
  POSTGRES_SLOT_RESTART_LAG_QUERY,
  POSTGRES_STREAMING_REPLICAS_QUERY,
  POSTGRES_WRITE_LAG_QUERY
} from '../../queries';
import { POSTGRES_CATEGORY_METRIC_NAMES } from '../metrics';
import ReplicationPane from '../replication-pane';
import {
  formatPostgresLagBytes,
  formatPostgresLagSeconds,
  postgresReplicationDimmed,
  postgresReplicationTabMode,
  readPostgresReplication,
  readPostgresReplicationLag,
  type PostgresReplicationMetricName
} from '../replication';
import type { PostgresMetricMap } from '../series';

beforeAll(() => {
  class ResizeObserver {
    observe() { return undefined; }
    unobserve() { return undefined; }
    disconnect() { return undefined; }
  }
  Object.defineProperty(window, 'ResizeObserver', { writable: true, value: ResizeObserver });
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

  it('wires the replication queries into the category fetch list', () => {
    const queries: Record<PostgresReplicationMetricName, string> = {
      postgresql_recovery_in_recovery: POSTGRES_RECOVERY_QUERY,
      postgresql_replication_streaming_replicas: POSTGRES_STREAMING_REPLICAS_QUERY,
      postgresql_replication_replication_slots: POSTGRES_REPLICATION_SLOTS_QUERY,
      postgresql_replication_write_lag_seconds: POSTGRES_WRITE_LAG_QUERY,
      postgresql_replication_flush_lag_seconds: POSTGRES_FLUSH_LAG_QUERY,
      postgresql_replication_replay_lag_seconds: POSTGRES_REPLAY_LAG_QUERY,
      postgresql_replication_slot_restart_lag_bytes: POSTGRES_SLOT_RESTART_LAG_QUERY
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
    expect(screen.getByText('本窗口暂无复制延迟或积压数据。')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-trends="none"]')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-lag="absent"]')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-lag-chart]')).toBeNull();
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
    expect(screen.getByText('本窗口暂无复制延迟或积压数据。')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-trends="none"]')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-status]')).toBeTruthy();
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
    expect(screen.getByText('本窗口暂无复制或恢复相关数据。请确认采集已开启并完成至少一个上报周期。')).toBeTruthy();
    expect(screen.queryByText('去开启复制')).toBeNull();
    expect(document.querySelector('[data-postgres-replication-card]')).toBeNull();
    expect(screen.queryByText('本窗口暂无复制延迟或积压数据。')).toBeNull();
    expect(screen.queryByText('延迟与积压')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '查看采集配置' }));
    expect(onOpenCollection).toHaveBeenCalledOnce();
  });
});

const lagCard = (key: string) => document.querySelector(`[data-postgres-replication-lag-card="${key}"]`);

describe('postgres replication lag', () => {
  it('formats seconds and bytes without inventing a non-zero', () => {
    expect(formatPostgresLagSeconds(0)).toBe('0s');
    expect(formatPostgresLagSeconds(1.2)).toBe('1.2s');
    expect(formatPostgresLagBytes(0)).toBe('0 B');
    expect(formatPostgresLagBytes(1.2 * 1024)).toBe('1.2 KiB');
  });

  it('keeps a real zero series and does not fill the other metrics', () => {
    const model = readPostgresReplicationLag(mapOf({
      postgresql_replication_write_lag_seconds: 0,
      postgresql_replication_flush_lag_seconds: 0,
      postgresql_replication_replay_lag_seconds: 0,
      postgresql_replication_slot_restart_lag_bytes: 0
    }), new Set());
    expect(model.state).toBe('ready');
    expect(model.trends).toBe('lag');
    model.cards.forEach((card) => {
      expect(card.value).toBe(0);
      expect(card.points).toEqual([{ time: 1, value1: 0 }]);
      expect(card.points.some((point) => point.value1 !== 0)).toBe(false);
    });
    expect(model.cards.map((card) => card.text)).toEqual(['0s', '0s', '0s', '0 B']);
    model.cards.forEach((card) => {
      const samples = card.points.map((point) => point.value1).filter((value): value is number => typeof value === 'number');
      const bounds = readableAxisBounds(samples, card.unit);
      expect(bounds).toBeTruthy();
      expect(seriesSitsOnAxisFloor(samples, bounds!.min, bounds!.max)).toBe(true);
    });
  });

  it('shows sampled lag and leaves an unsampled sibling as missing', () => {
    const model = readPostgresReplicationLag(mapOf({
      postgresql_replication_replay_lag_seconds: 1.2,
      postgresql_replication_slot_restart_lag_bytes: 1.2 * 1024
    }), new Set());
    expect(model.state).toBe('ready');
    expect(model.trends).toBe('lag');
    expect(model.cards.find((card) => card.key === 'write')?.value).toBeNull();
    expect(model.cards.find((card) => card.key === 'write')?.text).toBe('—');
    expect(model.cards.find((card) => card.key === 'write')?.points).toEqual([]);
    expect(model.cards.find((card) => card.key === 'replay')?.text).toBe('1.2s');
    expect(model.cards.find((card) => card.key === 'backlog')?.text).toBe('1.2 KiB');
    expect(model.cards.find((card) => card.key === 'backlog')?.points).toEqual([{ time: 1, value1: 1.2 * 1024 }]);
  });

  it('stays loading until the lag queries settle, then says the window has no samples', () => {
    const pending = readPostgresReplicationLag({}, new Set(['postgresql_replication_write_lag_seconds']));
    expect(pending.state).toBe('loading');
    expect(pending.trends).toBe('none');
    expect(readPostgresReplicationLag({}, new Set(), true).state).toBe('loading');
    const absent = readPostgresReplicationLag({}, new Set());
    expect(absent.state).toBe('absent');
    expect(absent.trends).toBe('none');
    expect(absent.cards.every((card) => card.value == null && card.points.length === 0)).toBe(true);
  });
});

describe('postgres replication lag pane', () => {
  const status = {
    postgresql_recovery_in_recovery: 0,
    postgresql_replication_streaming_replicas: 2,
    postgresql_replication_replication_slots: 2
  };

  it('draws the zero lag line and keeps the status cards', () => {
    render(
      <ReplicationPane
        metricMap={mapOf({
          ...status,
          postgresql_replication_write_lag_seconds: 0,
          postgresql_replication_flush_lag_seconds: 0,
          postgresql_replication_replay_lag_seconds: 0,
          postgresql_replication_slot_restart_lag_bytes: 0
        })}
        pendingMetricNames={new Set()}
      />
    );
    expect(screen.getByText('主库')).toBeTruthy();
    expect(screen.queryByText('复制状态未采集')).toBeNull();
    expect(screen.queryByText('本窗口暂无复制延迟或积压数据。')).toBeNull();
    expect(document.querySelector('[data-postgres-replication-trends="lag"]')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-lag="ready"]')).toBeTruthy();
    expect(lagCard('write')?.getAttribute('data-postgres-replication-lag-value')).toBe('0');
    expect(lagCard('backlog')?.textContent).toContain('0 B');
    expect(lagCard('write')?.textContent).toContain('0s');
    expect(document.querySelectorAll('[data-postgres-replication-lag-chart]')).toHaveLength(4);
    expect(document.querySelector('[data-postgres-replication-lag-chart="write"]')?.getAttribute('data-postgres-replication-lag-points')).toBe('1');
  });

  it('shows readable lag numbers when samples exist', () => {
    render(
      <ReplicationPane
        metricMap={mapOf({
          ...status,
          postgresql_replication_write_lag_seconds: 1.2,
          postgresql_replication_slot_restart_lag_bytes: 1.2 * 1024
        })}
        pendingMetricNames={new Set()}
      />
    );
    expect(lagCard('write')?.textContent).toContain('1.2s');
    expect(lagCard('flush')?.getAttribute('data-postgres-replication-lag-value')).toBe('missing');
    expect(lagCard('flush')?.textContent).toContain('—');
    expect(lagCard('backlog')?.textContent).toContain('1.2 KiB');
    expect(document.querySelectorAll('[data-postgres-replication-lag-chart]')).toHaveLength(2);
    expect(document.querySelector('[data-postgres-replication-lag-chart="flush"]')).toBeNull();
    expect(screen.getByText('流复制连接数')).toBeTruthy();
  });

  it('uses one loading place while lag queries are still out', () => {
    render(
      <ReplicationPane
        metricMap={mapOf(status)}
        pendingMetricNames={new Set([
          'postgresql_replication_write_lag_seconds',
          'postgresql_replication_flush_lag_seconds',
          'postgresql_replication_replay_lag_seconds',
          'postgresql_replication_slot_restart_lag_bytes'
        ])}
      />
    );
    expect(screen.getByText('主库')).toBeTruthy();
    expect(document.querySelector('[data-postgres-replication-lag="loading"]')).toBeTruthy();
    expect(document.querySelectorAll('[data-postgres-replication-lag="loading"]')).toHaveLength(1);
    expect(screen.queryByText('本窗口暂无复制延迟或积压数据。')).toBeNull();
    expect(document.querySelector('[data-postgres-replication-lag-chart]')).toBeNull();
    expect(document.querySelector('[data-postgres-replication-trends="none"]')).toBeTruthy();
    expect(screen.queryByText('复制状态未采集')).toBeNull();
  });

  it('does not cover status cards when only lag samples exist', () => {
    render(
      <ReplicationPane
        metricMap={mapOf({
          postgresql_replication_replay_lag_seconds: 0
        })}
        pendingMetricNames={new Set()}
      />
    );
    expect(screen.queryByText('复制状态未采集')).toBeNull();
    expect(document.querySelector('[data-postgres-replication-status]')).toBeTruthy();
    expect(card('role')?.getAttribute('data-postgres-replication-value')).toBe('missing');
    expect(lagCard('replay')?.getAttribute('data-postgres-replication-lag-value')).toBe('0');
    expect(document.querySelector('[data-postgres-replication-trends="lag"]')).toBeTruthy();
    expect(document.querySelectorAll('[data-postgres-replication-lag-chart]')).toHaveLength(1);
  });
});
