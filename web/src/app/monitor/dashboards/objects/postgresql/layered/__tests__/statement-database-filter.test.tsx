import { fireEvent, render, screen } from '@testing-library/react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useState } from 'react';
import { beforeAll, describe, expect, it, vi } from 'vitest';

import type { EntityTableRow } from '../../../host/entity-series';
import LayeredEntityTable, { type LayeredColumn } from '../../../host/layered/entity-table';
import {
  statementDatabaseFilters,
  statementMatchesDatabases
} from '../digest';

beforeAll(() => {
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

const rows = [
  { datname: 'zeta' },
  { datname: 'app' },
  { datname: 'app' },
  { datname: '' },
  { datname: '--' }
];

const entity = (key: string, datname: string): EntityTableRow => ({
  key,
  labels: { sql: `select ${key}`, datname: datname || '--' },
  values: {},
  series: {}
});

describe('statement database column filter', () => {
  it('builds unique sorted names and keeps an empty selection as every row', () => {
    expect(statementDatabaseFilters(rows).map((item) => item.text)).toEqual(['app', 'zeta']);
    expect(statementDatabaseFilters([{ datname: '--' }, { datname: '  ' }])).toEqual([]);
    const selected = ['zeta', 'app'];
    expect(rows.filter((row) => statementMatchesDatabases(row.datname, [])).map((row) => row.datname)).toEqual([
      'zeta',
      'app',
      'app',
      '',
      '--'
    ]);
    expect(rows.filter((row) => (
      statementMatchesDatabases(row.datname, selected)
      && `select ${row.datname}`.includes('select')
    )).map((row) => row.datname)).toEqual(['zeta', 'app', 'app']);
    expect(statementMatchesDatabases('', ['app'])).toBe(false);
    expect(statementMatchesDatabases('--', ['app'])).toBe(false);
  });

  it('uses the column funnel with confirm and reset, and has no database select', () => {
    const onChange = vi.fn();
    const filters = statementDatabaseFilters(rows);
    function Harness() {
      const [selected, setSelected] = useState<string[] | null>(null);
      const columns: LayeredColumn[] = [
        {
          key: 'sql',
          title: '语句',
          render: (row) => row.labels.sql
        },
        {
          key: 'datname',
          title: '数据库',
          render: (row) => row.labels.datname,
          filters,
          filterMultiple: true,
          filteredValue: selected
        }
      ];
      return (
        <LayeredEntityTable
          rows={[entity('app', 'app'), entity('zeta', 'zeta'), entity('main', 'main')]}
          columns={columns}
          loading={false}
          selectedKey="app"
          onSelect={() => undefined}
          onChange={(pagination, nextFilters, sorter, extra) => {
            const picked = nextFilters?.datname;
            setSelected(Array.isArray(picked) ? picked.map(String) : null);
            onChange(pagination, nextFilters, sorter, extra);
          }}
          toolbar={<input aria-label="搜索语句" />}
        />
      );
    }
    render(
      <ConfigProvider locale={zhCN}>
        <Harness />
      </ConfigProvider>
    );

    expect(screen.queryByRole('combobox', { name: '数据库' })).toBeNull();
    expect(screen.getByLabelText('搜索语句')).toBeTruthy();
    const openFunnel = () => {
      const header = screen.getAllByRole('columnheader', { name: /数据库/ })[0];
      fireEvent.click(header.querySelector('.ant-table-filter-trigger') as Element);
    };
    openFunnel();
    fireEvent.click(screen.getAllByRole('menuitem')[0]);
    fireEvent.click(screen.getByRole('menuitem', { name: 'zeta' }));
    fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }));

    const confirmed = onChange.mock.calls.at(-1)?.[1] as { datname?: string[] | null };
    expect([...(confirmed.datname || [])].sort()).toEqual(['app', 'zeta']);

    openFunnel();
    fireEvent.click(screen.getByRole('button', { name: /重置/ }));
    fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }));
    const reset = onChange.mock.calls.at(-1)?.[1] as { datname?: string[] | null };
    expect(reset.datname ?? []).toEqual([]);
  });
});
