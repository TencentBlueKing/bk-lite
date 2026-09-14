import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import AlarmBaseInfo from '../alarm-base-info';
import BaseInfo from '../../(pages)/alarms/components/baseInfo';
import type { AlarmTableDataItem } from '../../types/alarms';
import { SessionProvider } from 'next-auth/react';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => ({
    'alarmCommon.monitorSource': '监控源',
    'alarmCommon.expandSources': '展开全部',
    'alarmCommon.collapseSources': '收起',
    'alarmCommon.copySources': '复制监控源',
  }[key] || key) }),
}));
const copy = vi.fn();
vi.mock('@/hooks/useCopy', () => ({ useCopy: () => ({ copy }) }));
afterEach(() => { cleanup(); copy.mockClear(); });
beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() });
});

describe('告警详情监控源', () => {
  it.each(['page', 'component'])('%s 详情展示完整监控源并支持展开和复制', (variant) => {
    const sources = ['001', '1', 'k8s-prod', 'zabbix-test'];
    const detail = { push_source_ids: sources };
    render(<SessionProvider session={null}>{variant === 'page' ? <BaseInfo detail={detail as AlarmTableDataItem} /> : <AlarmBaseInfo detail={detail} />}</SessionProvider>);
    expect(screen.getByText('监控源')).toBeTruthy();
    expect(screen.getByText('001')).toBeTruthy();
    expect(screen.queryByText('zabbix-test')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /展开全部/ }));
    expect(screen.getByText('zabbix-test')).toBeTruthy();
    const copyButton = variant === 'page'
      ? screen.getByRole('button', { name: '复制监控源' })
      : screen.getAllByRole('button', { name: 'common.copy' }).find((button) => !(button as HTMLButtonElement).disabled)!;
    fireEvent.click(copyButton);
    expect(copy).toHaveBeenCalledWith('001\n1\nk8s-prod\nzabbix-test');
    fireEvent.click(screen.getByRole('button', { name: '收起' }));
    expect(screen.queryByText('zabbix-test')).toBeNull();
  });

  it('旧响应缺字段时显示监控源占位而不报错', () => {
    render(<AlarmBaseInfo detail={{}} />);
    expect(screen.getByText('监控源')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '复制监控源' })).toBeNull();
  });

  it.each(['page', 'component'])('%s 告警源展示派生名称而非单值快照', variant => {
    const detail = { source_names: ['平台A', '平台B,生产'], source_name: '旧快照' };
    render(<SessionProvider session={null}>{variant === 'page' ? <BaseInfo detail={detail as AlarmTableDataItem} /> : <AlarmBaseInfo detail={detail} />}</SessionProvider>);
    expect(screen.getByText('平台A')).toBeTruthy();
    expect(screen.getByText('平台B,生产')).toBeTruthy();
    expect(screen.queryByText('旧快照')).toBeNull();
  });
});
