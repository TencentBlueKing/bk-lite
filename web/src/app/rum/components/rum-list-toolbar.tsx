'use client';

import type { ReactNode } from 'react';

import ToolbarSplitShell from '@/components/toolbar-split-shell';

/**
 * RUM 列表/表格页工具条：标题/视图切换靠左，筛选→搜索→刷新→新建成组靠右。
 * 页面已有 `gap-4` 时用 flush，避免与 ToolbarSplitShell 默认 mb-4 叠距。
 */
export default function RumListToolbar({
  leading,
  trailing,
  className,
  leadingClassName,
  trailingClassName,
  spacing = 'flush',
}: {
  leading?: ReactNode;
  trailing?: ReactNode;
  className?: string;
  leadingClassName?: string;
  trailingClassName?: string;
  spacing?: 'default' | 'flush';
}) {
  return (
    <ToolbarSplitShell
      leading={leading}
      trailing={trailing}
      leadingClassName={leadingClassName}
      trailingClassName={trailingClassName}
      className={[spacing === 'flush' ? '!mb-0' : undefined, className]
        .filter(Boolean)
        .join(' ')}
    />
  );
}
