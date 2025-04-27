import React, { useEffect, useState } from 'react';
import { Tree, Spin, Input } from 'antd';
import { TreeItem } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';
import type { TreeProps, TreeDataNode } from 'antd';
import { cloneDeep } from 'lodash';
import { findTreeParentKey } from '@/app/monitor/utils/common';
import { TableDataItem, TreeSortData } from '@/app/monitor/types/monitor';

const { Search } = Input;

interface TreeComponentProps {
  data: TreeItem[];
  defaultSelectedKey?: string;
  loading?: boolean;
  onNodeSelect?: (key: string) => void;
  onNodeDrag?: (sortNodes: TreeSortData[], nodes: TreeDataNode[]) => void;
  draggable?: boolean;
}

const TreeComponent: React.FC<TreeComponentProps> = ({
  data,
  defaultSelectedKey,
  loading = false,
  onNodeSelect,
  onNodeDrag,
  draggable = false,
}) => {
  const { t } = useTranslation();
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [treeSearchValue, setTreeSearchValue] = useState<string>('');
  const [originalTreeData, setOriginalTreeData] = useState<TreeItem[]>([]);
  const [treeData, setTreeData] = useState<TreeItem[]>([]);

  useEffect(() => {
    if (defaultSelectedKey) {
      setSelectedKeys([defaultSelectedKey]);
      onNodeSelect?.(defaultSelectedKey);
    }
  }, [defaultSelectedKey]);

  useEffect(() => {
    setOriginalTreeData(data);
    setTreeData(data);
    setExpandedKeys(data.map((item) => item.key));
  }, [data]);

  const handleSelect = (selectedKeys: React.Key[], info: any) => {
    const isFirstLevel = !!info.node?.children?.length;
    if (!isFirstLevel && selectedKeys?.length) {
      setSelectedKeys(selectedKeys);
      onNodeSelect?.(selectedKeys[0] as string);
    }
  };

  const filterTree = (data: TreeItem[], searchValue: string): TreeItem[] => {
    return data
      .map((item: any) => {
        const children = filterTree(item.children || [], searchValue);
        if (
          item.title.toLowerCase().includes(searchValue.toLowerCase()) ||
          children.length
        ) {
          return {
            ...item,
            children,
          };
        }
        return null;
      })
      .filter(Boolean) as TreeItem[];
  };

  const handleSearchTree = (value: string) => {
    if (!value) {
      setTreeData(originalTreeData);
    } else {
      const filteredData = filterTree(originalTreeData, value);
      setTreeData(filteredData);
    }
  };

  const onDrop: TreeProps['onDrop'] = (info) => {
    const { dragNode, node: dropNode } = info;
    const dropKey = dropNode.key;
    const dragKey = dragNode.key;
    const dropPos = dropNode.pos.split('-');
    const dragPos = dragNode.pos.split('-');
    const dropLevel = dropPos.length; // 层级
    const dragLevel = dragPos.length; // 层级
    const dropPosition =
      info.dropPosition - Number(dropPos[dropPos.length - 1]);
    const _data = cloneDeep(data);
    // 一级节点只能在同级节点中排序
    if (dragLevel === 2) {
      if (
        dropNode.dragOverGapTop ||
        dropLevel === 2 ||
        dropNode.dragOverGapBottom
      ) {
        const targetKey = dropNode.dragOverGapBottom
          ? findTreeParentKey(data, dropKey)
          : dropKey;
        const draggingIndex = _data.findIndex((item) => item.key === dragKey);
        const targetIndex = _data.findIndex((item) => item.key === targetKey);
        const [draggedItem] = _data.splice(draggingIndex, 1);
        _data.splice(targetIndex, 0, draggedItem);
        onNodeDrag && onNodeDrag(getTreeSortData(_data), _data);
      }
      return;
    }
    // 子节点不能拖拽到非父节点内
    if (
      dragLevel === 3 &&
      (dragPos[0] !== dropPos[0] ||
        dragPos[1] !== dropPos[1] ||
        (dropLevel === 2 && info.dropToGap) ||
        (dropLevel === 3 && !info.dropToGap))
    ) {
      return;
    }
    const loop = (
      data: TreeDataNode[],
      key: React.Key,
      callback: (node: TreeDataNode, i: number, data: TreeDataNode[]) => void
    ) => {
      for (let i = 0; i < data.length; i++) {
        if (data[i].key === key) {
          return callback(data[i], i, data);
        }
        if (data[i].children) {
          loop(data[i].children!, key, callback);
        }
      }
    };
    let dragObj: TreeDataNode;
    loop(_data, dragKey, (item, index, arr) => {
      arr.splice(index, 1);
      dragObj = item;
    });
    if (!info.dropToGap) {
      loop(_data, dropKey, (item) => {
        item.children = item.children || [];
        item.children.unshift(dragObj);
      });
    } else {
      let ar: TreeDataNode[] = [];
      let i: number;
      loop(_data, dropKey, (_item, index, arr) => {
        ar = arr;
        i = index;
      });
      if (dropPosition === -1) {
        ar.splice(i!, 0, dragObj!);
      } else {
        ar.splice(i! + 1, 0, dragObj!);
      }
    }
    onNodeDrag && onNodeDrag(getTreeSortData(_data), _data);
  };

  const getTreeSortData = (data: any[]) => {
    return data.map((item) => {
      return {
        type: item.key,
        name_list: (item.children || []).map(
          (child: TableDataItem) => child.label
        ),
      };
    });
  };

  return (
    <div className="h-full">
      <Spin spinning={loading}>
        <Search
          className="mb-[10px]"
          placeholder={t('common.searchPlaceHolder')}
          value={treeSearchValue}
          enterButton
          onChange={(e) => setTreeSearchValue(e.target.value)}
          onSearch={handleSearchTree}
        />
        <Tree
          showLine
          draggable={draggable}
          selectedKeys={selectedKeys}
          expandedKeys={expandedKeys}
          treeData={treeData}
          onExpand={(keys) => setExpandedKeys(keys)}
          onSelect={handleSelect}
          onDrop={onDrop}
        />
      </Spin>
    </div>
  );
};

export default TreeComponent;
