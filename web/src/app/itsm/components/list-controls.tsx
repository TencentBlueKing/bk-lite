'use client';

import type { ComponentProps, ReactNode } from 'react';
import { Button, Input, Tabs, Tooltip, type TabsProps } from 'antd';
import { EditOutlined, EyeOutlined, ExportOutlined, DeleteOutlined, SettingOutlined, UnorderedListOutlined, PlayCircleOutlined, HistoryOutlined, LinkOutlined, ReloadOutlined, PlusOutlined } from '@ant-design/icons';
import ToolbarSplitShell from '@/components/toolbar-split-shell';
import MoreActionsDropdown, { type MoreActionsDropdownItem } from '@/components/more-actions-dropdown';

const icons = {
  edit: <EditOutlined />, view: <EyeOutlined />, export: <ExportOutlined />,
  delete: <DeleteOutlined />, configure: <SettingOutlined />, data: <UnorderedListOutlined />,
  publish: <PlayCircleOutlined />, history: <HistoryOutlined />, reference: <LinkOutlined />,
  retry: <ReloadOutlined />,
};

export interface ItsmRowAction extends MoreActionsDropdownItem {
  kind?: keyof typeof icons;
  hidden?: boolean;
  /** 低频及危险操作收在更多中。 */
  more?: boolean;
}

/** 调用方保留权限、节点条件及业务回调；这里只统一呈现。 */
export function ItsmRowActions({ items }: { items: ItsmRowAction[] }) {
  const visible = items.filter(item => !item.hidden);
  const direct = visible.filter(item => !item.more && !item.danger && !item.confirm && !item.permission).slice(0, 2);
  const overflow = visible.filter(item => !direct.includes(item));
  if (!visible.length) return null;
  return <span className="inline-flex items-center gap-1 whitespace-nowrap">
    {direct.map(item => <Tooltip key={item.key} title={item.label}>
      <Button type="text" size="small" aria-label={typeof item.label === 'string' ? item.label : item.key}
        disabled={item.disabled} icon={item.icon || icons[item.kind || 'edit']}
        onClick={event => { event.stopPropagation(); item.onClick?.(event); }} />
    </Tooltip>)}
    {overflow.length > 0 && <MoreActionsDropdown ariaLabel="更多操作" stopPropagation items={overflow.map(item => ({ ...item, icon: item.icon || icons[item.kind || 'edit'] }))} />}
  </span>;
}

export function ItsmListToolbar({ leading, filters, search, actions }: {
  leading?: ReactNode;
  filters?: ReactNode;
  search?: { value: string; onChange: (value: string) => void; placeholder?: string; label?: string };
  actions?: ReactNode;
}) {
  // DESIGN.md：左侧仅视图分组，筛选、搜索和公共操作成组靠右。
  return <ToolbarSplitShell leading={leading} leadingClassName="max-w-full"
    trailingClassName="min-w-0 max-w-full" trailing={<>
    {filters}
    {search && <Input.Search className="w-60 max-w-full" aria-label={search.label || search.placeholder || '搜索'}
      placeholder={search.placeholder || '搜索名称或标识'} allowClear value={search.value}
      onChange={event => search.onChange(event.target.value)} />}
    {actions}
  </>} />;
}

/** 与列表工具栏同行的无背景分组，沿用 AntD 键盘及溢出行为。 */
export function ItsmListTabs(props: Pick<TabsProps, 'activeKey' | 'onChange' | 'items'>) {
  return <Tabs {...props} type="line" className="min-w-0 max-w-full [&>.ant-tabs-nav]:!mb-0 [&>.ant-tabs-nav]:!bg-transparent [&_.ant-tabs-tab]:!bg-transparent" />;
}

export function ItsmCreateButton(props: Omit<ComponentProps<typeof Button>, 'icon' | 'type'>) {
  return <Button aria-label={typeof props.children === 'string' ? props.children : '新建'} {...props} type="primary" icon={<PlusOutlined />}>{props.children || '新建'}</Button>;
}
