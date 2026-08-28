'use client';

/**
 * 实体详情二级导航 After。
 * 整页一张工作台：菜单是内轨，不是旁边另贴的一层。
 * 选中用中性 fill。页内分区用 Tabs（供应商）；列表/配额无二级菜单。
 */

import type { ReactNode } from 'react';
import { Button } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { afterPanel } from './opspilot-after-system';

export interface AfterEntityNavItem {
  key: string;
  label: string;
  icon: string;
}

export function AfterEntityShell({
  name,
  items,
  active,
  children,
}: {
  name: string;
  items: AfterEntityNavItem[];
  active: string;
  children: ReactNode;
}) {
  return (
    <div className={`${afterPanel.card} flex min-h-[560px]`}>
      <aside className="flex w-[168px] shrink-0 flex-col border-r border-[var(--color-fill-2)] px-2 py-2">
        <div className="mb-2 flex min-h-8 items-center gap-0.5 px-0.5">
          <Button type="text" size="small" icon={<ArrowLeftOutlined />} className="h-7 w-7 shrink-0 px-0" />
          <span className="min-w-0 truncate text-[13px] font-medium tracking-tight text-[var(--color-text-1)]">
            {name}
          </span>
        </div>
        <nav className="flex flex-col gap-px">
          {items.map((item) => {
            const selected = item.key === active;
            return (
              <div
                key={item.key}
                className={`flex h-8 items-center gap-2 rounded-[6px] px-2 text-[13px] leading-none ${
                  selected
                    ? 'bg-[var(--color-fill-2)] font-medium text-[var(--color-text-1)]'
                    : 'text-[var(--color-text-2)] hover:bg-[var(--color-fill-1)]'
                }`}
              >
                <Icon
                  type={item.icon}
                  className={`text-base ${selected ? 'text-[var(--color-text-1)]' : 'text-[var(--color-text-3)]'}`}
                />
                {item.label}
              </div>
            );
          })}
        </nav>
      </aside>
      <div className="min-h-0 min-w-0 flex-1">{children}</div>
    </div>
  );
}

export const SKILL_NAV: AfterEntityNavItem[] = [
  { key: 'settings', label: '设置', icon: 'shezhi' },
  { key: 'publish', label: '发布', icon: 'channel1' },
];

export const STUDIO_NAV: AfterEntityNavItem[] = [
  { key: 'settings', label: '设置', icon: 'shezhi' },
  { key: 'channel', label: '通道', icon: 'channel1' },
  { key: 'logs', label: '日志', icon: 'talk-line' },
  { key: 'statistics', label: '统计', icon: 'tongji' },
  { key: 'api', label: '接口说明', icon: 'api' },
];

export const MEMORY_NAV: AfterEntityNavItem[] = [
  { key: 'config', label: '配置', icon: 'shezhi' },
  { key: 'memories', label: '记忆', icon: 'shiyongwendang' },
];

export const WIKI_NAV: AfterEntityNavItem[] = [
  { key: 'overview', label: '概览', icon: 'tongji' },
  { key: 'material', label: '素材', icon: 'shiyongwendang' },
  { key: 'knowledge', label: '知识', icon: 'zhishiku1' },
  { key: 'build', label: '构建', icon: 'biangengjilu' },
  { key: 'check', label: '检查', icon: 'ceshi' },
  { key: 'settings', label: '设置', icon: 'shezhi' },
];
