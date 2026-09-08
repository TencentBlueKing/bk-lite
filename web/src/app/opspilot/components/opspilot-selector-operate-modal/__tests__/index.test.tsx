import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OpspilotSelectorOperateModal from '../index';
import { resolveOptionIcon } from '@/app/opspilot/components/opspilot-selector-shared';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, defaultVal?: string) => defaultVal || key,
  }),
}));

afterEach(cleanup);

describe('resolveOptionIcon', () => {
  it('maps database and devops keywords to domain icons', () => {
    expect(resolveOptionIcon('MySQL 客户端')).toBe('mysql');
    expect(resolveOptionIcon('Redis 缓存查询')).toBe('redis');
    expect(resolveOptionIcon('Oracle 数据库')).toBe('oracle');
    expect(resolveOptionIcon('PostgreSQL 查询')).toBe('postgresql');
    expect(resolveOptionIcon('Elasticsearch 检索')).toBe('elasticsearch');
    expect(resolveOptionIcon('Shell执行工具')).toBe('linux');
    expect(resolveOptionIcon('HTTP 请求发送器')).toBe('api');
    expect(resolveOptionIcon('运维知识库')).toBe('zhishiku');
  });

  it('preserves valid custom icons and falls back to gongju', () => {
    expect(resolveOptionIcon('Custom Tool', 'custom-icon')).toBe('custom-icon');
    expect(resolveOptionIcon('Generic Tool', 'gongjuji')).toBe('gongju');
    expect(resolveOptionIcon('Generic Tool', undefined)).toBe('gongju');
  });
});

describe('OpspilotSelectorOperateModal', () => {
  const sampleOptions = [
    { id: 1, name: 'MySQL', description: '用于连接和操作 MySQL 数据库' },
    { id: 2, name: 'Redis', description: '用于读写 Redis 缓存与键值对' },
    { id: 3, name: 'Shell执行', description: '远程执行 Shell 命令与脚本' },
  ];

  it('renders options, displays selection count, and handles select toggles', () => {
    const onOk = vi.fn();
    const onCancel = vi.fn();

    render(
      <OpspilotSelectorOperateModal
        visible
        title="选择工具"
        options={sampleOptions}
        selectedOptions={[1]}
        onOk={onOk}
        onCancel={onCancel}
      />,
    );

    expect(screen.getByText('选择工具')).toBeTruthy();
    expect(screen.getByText('MySQL')).toBeTruthy();
    expect(screen.getByText('Redis')).toBeTruthy();
    expect(screen.getByText('Shell执行')).toBeTruthy();
    expect(screen.getByText('用于连接和操作 MySQL 数据库')).toBeTruthy();

    // Toggle Redis selection
    const redisCard = screen.getByText('Redis').closest('[role="button"]')!;
    fireEvent.click(redisCard);

    // Click confirm button
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    fireEvent.click(confirmBtn);

    expect(onOk).toHaveBeenCalledWith([1, 2]);
  });

  it('filters options when searching', () => {
    render(
      <OpspilotSelectorOperateModal
        visible
        title="选择工具"
        options={sampleOptions}
        selectedOptions={[]}
        onOk={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    const searchInput = screen.getByPlaceholderText(/search/i);
    fireEvent.change(searchInput, { target: { value: 'Shell' } });

    expect(screen.getByText('Shell执行')).toBeTruthy();
    expect(screen.queryByText('MySQL')).toBeNull();
    expect(screen.queryByText('Redis')).toBeNull();
  });
});
