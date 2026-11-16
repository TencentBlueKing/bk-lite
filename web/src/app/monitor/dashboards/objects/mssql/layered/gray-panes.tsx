'use client';

import { GrayTabEmptyState, ProSection } from '../../host/layered/pro-chrome';
import { MssqlHint } from './hint';

export function TopSqlPane() {
  return (
    <div data-mssql-pane="top_sql" data-mssql-empty="top_sql">
      <ProSection
        title="Top SQL"
        hint={(
          <MssqlHint
            kind="mssql-top-sql"
            title="Top SQL"
            body="就绪后可在此查看耗时靠前的语句。"
          />
        )}
      >
        <GrayTabEmptyState
          title="语句明细采集未就绪"
          hint="就绪后可在此查看耗时靠前的语句。本盘暂不展示估算或示例语句。"
        />
      </ProSection>
    </div>
  );
}

export function ReplicationPane() {
  return (
    <div data-mssql-pane="replication" data-mssql-empty="replication">
      <ProSection
        title="复制"
        hint={(
          <MssqlHint
            kind="mssql-replication"
            title="复制"
            body="开启后可在此查看副本延迟与队列。"
          />
        )}
      >
        <GrayTabEmptyState
          title="副本状态采集未开启"
          hint="开启后可在此查看副本延迟与队列。本盘暂不展示估算值。"
        />
      </ProSection>
    </div>
  );
}
