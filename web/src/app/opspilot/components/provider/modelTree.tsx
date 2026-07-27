import React, { useMemo, useState } from 'react';
import { Tree, Button, Modal, Input } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import type { DataNode } from 'antd/lib/tree';
import { ModelTreeProps } from '@/app/opspilot/types/provider';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import MoreActionsDropdown from '@/components/more-actions-dropdown';
import { ModelTreeSkeleton } from '@/app/opspilot/components/provider/skeleton';

const { Search } = Input;

const ModelTree: React.FC<ModelTreeProps> = ({
  groups,
  selectedGroupId,
  onGroupSelect,
  onGroupAdd,
  onGroupEdit,
  onGroupDelete,
  onGroupOrderChange,
  loading
}) => {
  const { t } = useTranslation();
  const [expandedKeys, setExpandedKeys] = useState<string[]>(['all']);
  const [searchValue, setSearchValue] = useState<string>('');

  // Generate tree data structure
  const treeData = useMemo(() => {
    const totalCount = groups.reduce((sum, group) => sum + (group.count || 0), 0);

    const allNode: DataNode = {
      key: 'all',
      title: (
        <div className="flex justify-between items-center w-full text-xs">
          <span>{t('common.all')}</span>
          <div className="flex items-center gap-1">
            <span className="shrink-0 text-xs text-(--color-text-3)">({totalCount})</span>
            <div className="h-4 w-4 shrink-0"></div>
          </div>
        </div>
      ),
      selectable: true,
    };

    // Filter groups based on search value
    const filteredGroups = searchValue
      ? groups.filter(group =>
        (group.display_name || group.name).toLowerCase().includes(searchValue.toLowerCase())
      )
      : groups;

    const groupNodes: DataNode[] = filteredGroups
      .sort((a, b) => (a.index || 0) - (b.index || 0))
      .map(group => ({
        key: String(group.id),
        title: (
          <div className="flex justify-between items-center w-full text-xs group">
            <span className="flex-1 mr-2 overflow-hidden text-ellipsis whitespace-nowrap">
              {group.display_name || group.name}
            </span>
            <div className="flex items-center gap-1">
              <span className="shrink-0 text-xs text-(--color-text-3)">({group.count || 0})</span>
              {!group.is_build_in ? (
                <MoreActionsDropdown
                  items={[
                    {
                      key: 'edit',
                      icon: <EditOutlined />,
                      label: t('common.edit'),
                      onClick: () => onGroupEdit(group),
                    },
                    {
                      key: 'delete',
                      icon: <DeleteOutlined />,
                      label: t('common.delete'),
                      danger: true,
                      onClick: () => {
                        Modal.confirm({
                          title: t('provider.group.deleteConfirm'),
                          content: `${t('provider.group.deleteConfirmContent')} "${group.display_name || group.name}"`,
                          onOk: () => onGroupDelete(group.id)
                        });
                      },
                    },
                  ]}
                  buttonClassName="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-all text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                />
              ) : (
                // Placeholder for built-in groups to align count display
                <div className="h-4 w-4 shrink-0"></div>
              )}
            </div>
          </div>
        ),
        selectable: true,
      }));

    return [allNode, ...groupNodes];
  }, [groups, searchValue, t, onGroupEdit, onGroupDelete]);

  const handleSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      onGroupSelect(selectedKeys[0] as string);
    }
  };

  const handleExpand = (expandedKeys: React.Key[]) => {
    setExpandedKeys(expandedKeys.map(key => String(key)));
  };

  const handleDrop = async (info: any) => {
    const dropKey = info.node.key;
    const dragKey = info.dragNode.key;

    // Prevent dragging to/from "all" node
    if (dropKey === 'all' || dragKey === 'all') return;

    const dragGroup = groups.find(g => String(g.id) === dragKey);
    const dropGroup = groups.find(g => String(g.id) === dropKey);

    // Validation: ensure both groups exist and not dragging to self
    if (!dragGroup || !dropGroup || dragGroup.id === dropGroup.id) return;

    const targetIndex = dropGroup.index || 0;

    // Validation: ensure callback function exists
    if (!onGroupOrderChange) {
      console.error('onGroupOrderChange function is not provided');
      return;
    }

    try {
      // Call API to update group order
      await onGroupOrderChange([{ id: dragGroup.id, index: targetIndex }]);
    } catch (error) {
      console.error('Failed to update group order:', error);
    }
  };

  // Show skeleton during loading
  if (loading) {
    return <ModelTreeSkeleton />;
  }

  return (
    <div className="h-full flex flex-col rounded-md bg-(--color-bg-1)">
      <div className="flex items-center justify-between gap-2 border-b border-(--color-border-2) p-3">
        <Search
          placeholder={`${t('common.search')}...`}
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          allowClear
          size="small"
          className="flex-1"
        />
        <PermissionWrapper requiredPermissions={['Setting']}>
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            onClick={onGroupAdd}
            className="flex shrink-0 items-center justify-center"
          />
        </PermissionWrapper>
      </div>

      <div className="flex-1 p-2 overflow-auto">
        <Tree
          showLine={{ showLeafIcon: false }}
          blockNode
          treeData={treeData}
          selectedKeys={[selectedGroupId]}
          expandedKeys={expandedKeys}
          onExpand={handleExpand}
          onSelect={handleSelect}
          onDrop={handleDrop}
          draggable={{
            icon: false,
            nodeDraggable: (node) => node.key !== 'all'
          }}
          allowDrop={({ dropNode }) => dropNode.key !== 'all'}
          className="[&_.ant-tree-node-content-wrapper]:px-2 [&_.ant-tree-node-content-wrapper]:py-1 [&_.ant-tree-node-content-wrapper]:rounded [&_.ant-tree-node-content-wrapper]:transition-all [&_.ant-tree-node-content-wrapper:hover]:bg-(--color-fill-1) [&_.ant-tree-node-selected_.ant-tree-node-content-wrapper]:bg-(--color-primary-bg-active) [&_.ant-tree-node-selected_.ant-tree-node-content-wrapper]:text-(--color-primary)"
        />
      </div>
    </div>
  );
};

export default ModelTree;
