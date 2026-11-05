'use client';

import { GrayTabEmptyState, ProDashLoading, ThinTimeSeries } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import { mongoReplicaStateLabel } from './architecture';
import { MongoHint } from './hint';
import { MONGODB_PALETTE } from './metrics';
import {
  mongoDurationText,
  mongoMemberHealthText,
  mongoReplicationLoad,
  type MongoReplicationLoad
} from './replication';
import { mongoLatest, mongoMerged, mongoPoints, type MongoMetricMap } from './series';

const EMPTY = {
  title: '当前没有副本集读数',
  hint: '本窗口没有复制延迟、oplog 窗口或成员健康。单机实例通常没有这些读数。'
};

const ABSENT = '本窗口暂无这条读数。';

const CARDS = [
  {
    key: 'lag',
    metric: 'mongodb_repl_lag',
    title: '复制延迟',
    unit: 's' as const,
    color: MONGODB_PALETTE.orange,
    body: '本实例落后主库的时间。主库自己通常没有落后，读数是 0 秒。没有读数时显示 —。'
  },
  {
    key: 'oplog',
    metric: 'mongodb_repl_oplog_window_sec',
    title: 'oplog 窗口',
    unit: 's' as const,
    color: MONGODB_PALETTE.cyan,
    body: '操作日志还能覆盖多久的变更。窗口过短时，断开较久的成员可能无法自动接上。'
  },
  {
    key: 'members',
    metric: 'mongodb_repl_member_health',
    title: '成员健康',
    unit: 'none' as const,
    color: MONGODB_PALETTE.green,
    body: '本实例在副本集里是否正常。正常表示可以参与复制，异常表示当前不可用。'
  }
] as const;

function ReplicationCard({
  cardKey,
  title,
  body,
  headline,
  tone,
  note,
  loading,
  sample,
  unit,
  color,
  points
}: {
  cardKey: string;
  title: string;
  body: string;
  headline: string;
  tone?: string;
  note?: string;
  loading: boolean;
  sample: number | null;
  unit: 's' | 'none';
  color: string;
  points: ReturnType<typeof mongoMerged>;
}) {
  return (
    <section
      className={`${classic.panel} ${host.chartPanel}`}
      data-mongodb-replication-card={cardKey}
      data-mongodb-replication-value={loading ? 'loading' : sample == null ? 'missing' : String(sample)}
    >
      <div className={host.chartHead}>
        <div className={host.chartTitle}>
          <span className="inline-flex items-center gap-1">
            {title}
            <MongoHint kind={`mongo-repl-${cardKey}`} title={title} body={body} />
          </span>
        </div>
      </div>
      {loading ? <ProDashLoading size="small" /> : (
        <div
          className="text-[22px] font-semibold leading-7 text-[var(--color-text-1)]"
          style={tone ? { color: tone } : undefined}
        >
          {headline}
        </div>
      )}
      {note ? (
        <p className="m-0 text-[12px] leading-5 text-[var(--color-text-3)]" data-mongodb-replica-state={note}>
          {note}
        </p>
      ) : null}
      {points.length > 0 ? (
        <ThinTimeSeries
          bare
          pinAxisZero
          className={host.focusChart}
          title=""
          unit={unit}
          data={points}
          legends={[{ label: title, color }]}
        />
      ) : loading ? null : (
        <p className="m-0 text-[13px] leading-5 text-[var(--color-text-3)]">{ABSENT}</p>
      )}
    </section>
  );
}

export default function ReplicationPane({
  metricMap,
  pendingMetricNames,
  booting = false
}: {
  metricMap: MongoMetricMap;
  pendingMetricNames: ReadonlySet<string>;
  booting?: boolean;
}) {
  const load: MongoReplicationLoad = mongoReplicationLoad(metricMap, pendingMetricNames, booting);
  if (load === 'not_collected') {
    return (
      <div data-mongodb-pane="replication" data-mongodb-replication="empty" className="flex flex-col gap-3">
        <GrayTabEmptyState title={EMPTY.title} hint={EMPTY.hint} />
      </div>
    );
  }

  const state = mongoLatest(metricMap, 'mongodb_repl_state');
  const stateLabel = mongoReplicaStateLabel(state);

  return (
    <div
      data-mongodb-pane="replication"
      data-mongodb-replication={load === 'loading' ? 'loading' : 'ready'}
      className="flex flex-col gap-3"
    >
      <div className={host.chartGrid3}>
        {CARDS.map((card) => {
          const sample = mongoLatest(metricMap, card.metric);
          const points = mongoPoints(metricMap, card.metric);
          const plotted = mongoMerged(metricMap, [{ name: card.metric, label: card.title }]);
          const waiting = sample == null && points.length === 0 && (
            load === 'loading' || pendingMetricNames.has(card.metric)
          );
          const health = card.key === 'members' ? mongoMemberHealthText(sample) : null;
          return (
            <ReplicationCard
              key={card.key}
              cardKey={card.key}
              title={card.title}
              body={card.body}
              headline={health ? health.text : mongoDurationText(sample)}
              tone={health?.tone || (sample == null ? undefined : card.color)}
              note={card.key === 'members' && stateLabel ? stateLabel : undefined}
              loading={waiting}
              sample={sample}
              unit={card.unit}
              color={card.color}
              points={plotted}
            />
          );
        })}
      </div>
    </div>
  );
}
