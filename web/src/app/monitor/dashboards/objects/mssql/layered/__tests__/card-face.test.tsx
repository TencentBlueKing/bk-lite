import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
import { IntlProvider } from 'react-intl';
import { describe, expect, it } from 'vitest';
import { HorizontalBarPanel } from '@/app/monitor/components/monitor-dashboard-widgets/horizontal-bar-panel';
import { mssqlCardFace, mssqlDeferEmpty } from '../card-face';
import { MssqlSeriesReadout } from '../trend';

function mount(node: ReactNode) {
  return render(<IntlProvider locale="zh" messages={{}}>{node}</IntlProvider>);
}

describe('mssql card face', () => {
  it('查询进行中只算加载中，结束后才区分空态和有数', () => {
    expect(mssqlCardFace(true, false)).toBe('loading');
    expect(mssqlCardFace(true, true)).toBe('loading');
    expect(mssqlCardFace(false, false)).toBe('empty');
    expect(mssqlCardFace(false, true)).toBe('ready');
  });

  it('整批未结束时，没有点的卡继续加载；有点（含 0）不再空等', () => {
    expect(mssqlDeferEmpty(false, false, true)).toBe(true);
    expect(mssqlDeferEmpty(false, true, false)).toBe(true);
    expect(mssqlDeferEmpty(false, false, false)).toBe(false);
    expect(mssqlDeferEmpty(true, false, true)).toBe(false);
    expect(mssqlCardFace(mssqlDeferEmpty(false, false, true), false)).toBe('loading');
    expect(mssqlCardFace(mssqlDeferEmpty(false, false, false), false)).toBe('empty');
    expect(mssqlCardFace(mssqlDeferEmpty(true, true, true), true)).toBe('ready');
  });

  it('占位不走空态组件，加载中和暂无数据不会叠在同一张卡', () => {
    const loading = mount(
      <HorizontalBarPanel
        title="数据库压力排行"
        items={[]}
        isEmpty
        emptyDescription="本窗口暂无数据"
        placeholder={<span>加载中</span>}
        styles={{}}
      />
    );
    expect(screen.getByText('加载中')).toBeTruthy();
    expect(loading.container.querySelector('.ant-empty')).toBeNull();
    expect(loading.container.textContent).not.toContain('本窗口暂无数据');
    expect(loading.container.textContent).not.toContain('暂无数据');

    loading.unmount();
    const empty = mount(
      <HorizontalBarPanel
        title="数据库压力排行"
        items={[]}
        placeholder={<span>本窗口暂无数据</span>}
        styles={{}}
      />
    );
    expect(screen.getByText('本窗口暂无数据')).toBeTruthy();
    expect(empty.container.querySelector('.ant-empty')).toBeNull();
    expect(empty.container.textContent).not.toContain('加载中');
  });
});

describe('mssql clerk readout', () => {
  it('有数时一行一个维度，竖排，不换行展开', () => {
    const { container } = render(
      <MssqlSeriesReadout
        items={[
          { label: 'CACHESTORE_SQLCP', color: '#36f', reading: '12 MiB' },
          { label: 'MEMORYCLERK_SQLBUFFERPOOL', color: '#f63', reading: '8 MiB' }
        ]}
      />
    );
    const list = container.querySelector('[data-mssql-series-readout]');
    expect(list?.getAttribute('data-mssql-series-readout')).toBe('rows');
    expect(list?.className).toContain('flex-col');
    expect(list?.className).not.toContain('flex-wrap');
    expect(list?.querySelectorAll('li')).toHaveLength(2);
    expect(screen.getByText('CACHESTORE_SQLCP')).toBeTruthy();
    expect(screen.getByText('12 MiB')).toBeTruthy();
    expect(screen.getByText('MEMORYCLERK_SQLBUFFERPOOL')).toBeTruthy();
  });

  it('无数时不留空列表', () => {
    const { container } = render(<MssqlSeriesReadout items={[]} />);
    expect(container.querySelector('[data-mssql-series-readout]')).toBeNull();
  });
});
