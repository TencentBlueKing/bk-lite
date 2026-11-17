'use client';

import {
  GrayTabEmptyState,
  ProDashLoading,
  ProSection,
  ThinTimeSeries,
  proChromeClass
} from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
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

const STATUS = [
  {
    key: 'lag',
    metric: 'mongodb_repl_lag',
    title: '复制延迟',
    color: MONGODB_PALETTE.orange,
    body: '本实例落后主库的时间。主库自己通常没有落后，读数是 0 秒。没有读数时显示 —。'
  },
  {
    key: 'oplog',
    metric: 'mongodb_repl_oplog_window_sec',
    title: 'oplog 窗口',
    color: MONGODB_PALETTE.cyan,
    body: '操作日志还能覆盖多久的变更。窗口过短时，断开较久的成员可能无法自动接上。'
  },
  {
    key: 'members',
    metric: 'mongodb_repl_member_health',
    title: '成员健康',
    color: MONGODB_PALETTE.green,
    body: '本实例在副本集里是否正常。正常表示可以参与复制，异常表示当前不可用。'
  }
] as const;

const TRENDS = [
  {
    key: 'lag',
    metric: 'mongodb_repl_lag',
    title: '复制延迟',
    unit: 's' as const,
    color: MONGODB_PALETTE.orange,
    body: '本实例落后主库的时间变化。'
  },
  {
    key: 'oplog',
    metric: 'mongodb_repl_oplog_window_sec',
    title: 'oplog 窗口',
    unit: 's' as const,
    color: MONGODB_PALETTE.cyan,
    body: '操作日志还能覆盖的时长变化。'
  }
] as const;

/** 单卡没有读数时只留 —，不补 0，也不在状态卡里画折线。 */
function QuietReading() {
  return (
    <div className={proChromeClass.kpiValue} data-mongodb-replication-quiet="">
      —
    </div>
  );
}

function StatusCard({
  cardKey,
  title,
  body,
  text,
  tone,
  loading,
  sample
}: {
  cardKey: string;
  title: string;
  body: string;
  text: string;
  tone?: string;
  loading: boolean;
  sample: number | null;
}) {
  return (
    <div
      className={`${proChromeClass.kpiCard}${loading ? ` ${proChromeClass.kpiCardLoading}` : ''}`}
      data-mongodb-replication-card={cardKey}
      data-mongodb-replication-value={loading ? 'loading' : sample == null ? 'missing' : String(sample)}
    >
      {loading ? <ProDashLoading /> : (
        <>
          <div className={`${proChromeClass.kpiLabel} inline-flex max-w-full items-center gap-1 !overflow-visible`}>
            <span className="min-w-0 truncate">{title}</span>
            <MongoHint kind={`mongo-repl-${cardKey}`} title={title} body={body} />
          </div>
          {sample == null ? <QuietReading /> : (
            <div className={proChromeClass.kpiValue} style={tone ? { color: tone } : undefined}>
              {text}
            </div>
          )}
        </>
      )}
    </div>
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
      <div data-mongodb-pane="replication" data-mongodb-replication="empty">
        <GrayTabEmptyState title={EMPTY.title} hint={EMPTY.hint} />
      </div>
    );
  }

  const trends = TRENDS.filter((card) => mongoPoints(metricMap, card.metric).length > 0);

  return (
    <div
      data-mongodb-pane="replication"
      data-mongodb-replication={load === 'loading' ? 'loading' : 'ready'}
      className="flex w-full min-w-0 shrink-0 flex-col gap-4"
    >
      <ProSection title="状态">
        <div
          className={proChromeClass.kpiGrid}
          style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}
          data-mongodb-replication-status=""
        >
          {STATUS.map((card) => {
            const sample = mongoLatest(metricMap, card.metric);
            const waiting = sample == null && (
              load === 'loading' || pendingMetricNames.has(card.metric)
            );
            const health = card.key === 'members' ? mongoMemberHealthText(sample) : null;
            return (
              <StatusCard
                key={card.key}
                cardKey={card.key}
                title={card.title}
                body={card.body}
                text={health ? health.text : mongoDurationText(sample)}
                tone={health?.tone}
                loading={waiting}
                sample={sample}
              />
            );
          })}
        </div>
      </ProSection>
      {trends.length > 0 ? (
        <ProSection title="趋势">
          <div className={host.chartGrid2} data-mongodb-replication-trends="">
            {trends.map((card) => (
              <ThinTimeSeries
                key={card.key}
                title={card.title}
                unit={card.unit}
                pinAxisZero
                data={mongoMerged(metricMap, [{ name: card.metric, label: card.title }])}
                legends={[{ label: card.title, color: card.color }]}
                emptyText="本窗口暂无这条读数。"
                hintNode={<MongoHint kind={`mongo-repl-trend-${card.key}`} title={card.title} body={card.body} />}
              />
            ))}
          </div>
        </ProSection>
      ) : null}
    </div>
  );
}
