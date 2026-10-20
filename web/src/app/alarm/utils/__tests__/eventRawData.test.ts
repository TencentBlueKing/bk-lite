import { describe, expect, it } from 'vitest';

import { presentEventRawData } from '../eventRawData';

describe('presentEventRawData', () => {
  it('把事件丰富结果附在原始数据展示副本上', () => {
    const raw = { title: 'cpu', resource_type: 'Host' };
    const enrichment = { cmdb: { ip_addr: '10.11.27.147', inst_name: 'host' } };

    const presented = presentEventRawData({ raw_data: raw, enrichment });

    expect(presented).toEqual({
      title: 'cpu',
      resource_type: 'Host',
      enrichment,
    });
    expect(raw).toEqual({ title: 'cpu', resource_type: 'Host' });
  });

  it('没有丰富结果时仍展示空对象，避免原始数据看起来像没跑过丰富', () => {
    expect(presentEventRawData({ raw_data: { title: 'cpu' } })).toEqual({
      title: 'cpu',
      enrichment: {},
    });
  });

  it('原始数据不是对象时单独包一层，不丢掉丰富结果', () => {
    expect(presentEventRawData({ raw_data: 'plain', enrichment: { cmdb: { owner: 'alice' } } })).toEqual({
      raw_data: 'plain',
      enrichment: { cmdb: { owner: 'alice' } },
    });
  });
});
