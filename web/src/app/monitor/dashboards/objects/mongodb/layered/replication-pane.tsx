'use client';

import { GrayTabEmptyState } from '../../host/layered/pro-chrome';
import host from '../../host/layered/layered.module.scss';
import classic from '../../host/index.module.scss';
import { MongoHint } from './hint';

const LEAD = '复制延迟、oplog 窗口与成员健康暂未接入本盘。本环境先验对象为单机时，即使后续扩采也可能暂时没有副本集读数。接入并有点后，可在此查看复制健康。';

const CARDS = [
  {
    key: 'lag',
    title: '复制延迟',
    face: '接入并有点后可查看。',
    body: '主从之间落后的时间。'
  },
  {
    key: 'oplog',
    title: 'oplog 窗口',
    face: '接入并有点后可查看。',
    body: '操作日志还能覆盖的时长。'
  },
  {
    key: 'members',
    title: '成员健康',
    face: '接入并有点后可查看。',
    body: '副本集里各成员是否正常。'
  }
] as const;

/** 复制签只放说明，不绑目录外指标，也不画延迟或成员点。 */
export default function ReplicationPane() {
  return (
    <div data-mongodb-pane="replication" data-mongodb-replication="gray" className="flex flex-col gap-3">
      <GrayTabEmptyState title="复制监控尚未就绪" hint={LEAD} />
      <div className={host.chartGrid3}>
        {CARDS.map((card) => (
          <section
            key={card.key}
            className={`${classic.panel} ${host.chartPanel}`}
            data-mongodb-replication-card={card.key}
          >
            <div className={host.chartHead}>
              <div className={host.chartTitle}>
                <span className="inline-flex items-center gap-1">
                  {card.title}
                  <MongoHint kind={`mongo-repl-${card.key}`} title={card.title} body={card.body} />
                </span>
              </div>
            </div>
            <p className="m-0 text-[13px] font-medium leading-5 text-[var(--color-text-2)]">{card.face}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
