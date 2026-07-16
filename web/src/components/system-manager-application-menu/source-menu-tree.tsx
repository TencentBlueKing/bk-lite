'use client';

import React, { useMemo } from 'react';
import { Tree, Spin } from 'antd';
import { FolderOutlined, FileOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import PanelShell from '@/components/panel-shell';
import SectionHeader from '@/components/section-header';
import type { DataNode } from 'antd/lib/tree';
import type { SourceMenuNode } from '@/components/system-manager-application-menu/types';

interface SourceMenuTreeProps {
  sourceMenus: SourceMenuNode[];
  selectedKeys: string[];
  loading: boolean;
  disabled?: boolean;
  onCheck: (checkedKeys: any) => void;
}

const SourceMenuTree: React.FC<SourceMenuTreeProps> = ({
  sourceMenus,
  selectedKeys,
  loading,
  disabled = false,
  onCheck,
}) => {
  const { t } = useTranslation();

  const treeData: DataNode[] = sourceMenus.map(menu => {
    if (menu.isDetailMode) {
      return {
        key: menu.name,
        title: menu.display_name,
        icon: menu.icon ? <Icon className="!h-full flex items-center" type={menu.icon} /> : <FolderOutlined />,
        checkable: true,
        selectable: false,
        isLeaf: true,
      };
    }

    return {
      key: menu.name,
      title: menu.display_name,
      icon: menu.icon ? <Icon className="!h-full flex items-center" type={menu.icon} /> : <FolderOutlined />,
      checkable: false,
      children: menu.children?.map(child => ({
        key: child.name,
        title: child.display_name,
        icon: child.icon ? <Icon className="!h-full flex items-center" type={child.icon} /> : <FileOutlined />,
        checkable: true,
        isLeaf: true,
        data: child,
      }))
    };
  });

  const expandedKeys = useMemo(() => {
    return sourceMenus
      .filter(menu => !menu.isDetailMode)
      .map(menu => menu.name);
  }, [sourceMenus]);

  return (
    <PanelShell
      className="w-[300px] rounded-lg bg-[var(--color-bg)]"
      headerClassName="border-b border-[var(--color-border-2)] px-4 py-3"
      bodyClassName="p-3"
      header={(
        <SectionHeader
          className="mb-0"
          title={t('system.menu.sourceMenus')}
          titleClassName="text-sm font-medium"
        />
      )}
    >
      <Spin spinning={loading}>
        <Tree
          showLine
          showIcon
          checkable
          disabled={disabled}
          expandedKeys={expandedKeys}
          checkedKeys={selectedKeys}
          onCheck={onCheck}
          treeData={treeData}
          className="source-menu-tree"
        />
      </Spin>
    </PanelShell>
  );
};

export default SourceMenuTree;
