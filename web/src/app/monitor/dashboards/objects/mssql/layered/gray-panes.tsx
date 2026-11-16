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
            body="按语句查看一段时间内耗时靠前的查询。当前还没有这类历史排行，不是这台实例缺少数据。"
          />
        )}
      >
        <GrayTabEmptyState
          title="当前还没有按语句耗时的历史排行，不是这台实例缺少数据。"
          hint="本签暂不展示估算或示例语句。"
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
            body="实例启用 Always On 并开启采集后，可在此查看副本延迟与队列。未启用 Always On 的实例，开启采集也不会有副本数据。"
          />
        )}
      >
        <GrayTabEmptyState title="副本状态采集未开启。" />
      </ProSection>
    </div>
  );
}
