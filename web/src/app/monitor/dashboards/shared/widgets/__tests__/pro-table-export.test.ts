import { describe, expect, it } from 'vitest';

import { buildProTableCsv, proTableFileName } from '../pro-table-export';

describe('pro table export', () => {
  it('names the file with the object, tab, and table', () => {
    expect(proTableFileName('nginx', '请求与站点', '站点')).toBe('nginx-请求与站点-站点.csv');
    expect(proTableFileName('nginx', '请求与站点', '过滤器')).toBe('nginx-请求与站点-过滤器.csv');
    expect(proTableFileName('nginx', '上游', '上游')).toBe('nginx-上游-上游.csv');
  });

  it('keeps the total row after the current body order', () => {
    const csv = buildProTableCsv(
      ['站点', '5xx'],
      [
        ['b', '2'],
        ['a', '0'],
        ['全部站点', '9']
      ]
    );
    expect(csv.split('\r\n')).toEqual(['站点,5xx', 'b,2', 'a,0', '全部站点,9']);
  });
});