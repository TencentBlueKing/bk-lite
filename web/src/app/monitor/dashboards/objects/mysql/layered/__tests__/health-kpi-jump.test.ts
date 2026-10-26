import { describe, expect, it } from 'vitest';
import { mysqlHealthKpiJump } from '../ia';

describe('mysqlHealthKpiJump', () => {
  it('左四卡跳到对应折线，运行时长和告警不跳', () => {
    expect(mysqlHealthKpiJump('connections')).toEqual({ tab: 'performance', anchor: 'connections' });
    expect(mysqlHealthKpiJump('qps')).toEqual({ tab: 'performance', anchor: 'throughput' });
    expect(mysqlHealthKpiJump('slow')).toEqual({ tab: 'performance', anchor: 'scan-lock' });
    expect(mysqlHealthKpiJump('replication')).toEqual({ tab: 'replication', anchor: 'mysql-repl-trend' });
    expect(mysqlHealthKpiJump('uptime')).toBeNull();
    expect(mysqlHealthKpiJump('alerts')).toBeNull();
  });
});
