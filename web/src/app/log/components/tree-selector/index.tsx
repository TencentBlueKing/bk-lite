import React, { useEffect, useState } from 'react';
import { Tree, Spin, Input, Empty } from 'antd';
import { TreeItem, TableDataItem } from '@/app/log/types';
import { useTranslation } from '@/utils/i18n';
import type { TreeProps, TreeDataNode } from 'antd';
import { cloneDeep } from 'lodash';
import { findTreeParentKey } from '@/app/log/utils/common';
import { TreeSortData } from '@/app/log/types/event';
import treeStyle from './index.module.scss';

const { Search } = Input;

interface TreeComponentProps {
  data: TreeItem[];
  defaultSelectedKey?: string;
  loading?: boolean;
  draggable?: boolean;
  showAllMenu?: boolean;
  style?: Record<string, string | number>;
  inputStyle?: Record<string, string | number>;
  onNodeSelect?: (key: string) => void;
  onNodeDrag?: (sortNodes: TreeSortData[], nodes: TreeDataNode[]) => void;
}

const TreeComponent: React.FC<TreeComponentProps> = ({
  data,
  defaultSelectedKey,
  loading = false,
  draggable = false,
  showAllMenu = false,
  inputStyle = {},
  style = { width: 200, height: 'calc(100vh - 146px)' },
  onNodeSelect,
  onNodeDrag,
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
    const filteredData = filterAllMenu(data);
    setTreeData(filteredData);
    setExpandedKeys(filteredData.map((item) => item.key));
  }, [data]);

  const filterAllMenu = (data: TreeItem[], searchValue: string = '') => {
    if (!showAllMenu) {
      return data.filter((item) => item.key !== 'all');
    }
    if (searchValue) {
      return data.filter((item) => item.key !== 'all');
    }
    return data;
  };

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
      const filteredData = filterAllMenu(originalTreeData);
      setTreeData(filteredData);
      setExpandedKeys(filteredData.map((item) => item.key));
      return;
    }
    const filteredData = filterTree(originalTreeData, value);
    const allMenuFilteredData = filterAllMenu(filteredData, value);
    // 检查是否只有一级菜单匹配，如果是，则展开并显示所有子节点
    const expandedFilteredData = allMenuFilteredData.map((item: any) => {
      // 如果一级菜单匹配但没有子节点匹配到搜索条件，则显示所有子节点
      const originalItem = originalTreeData.find(
        (orig) => orig.key === item.key
      );
      if (
        originalItem &&
        item.title.toLowerCase().includes(value.toLowerCase()) &&
        (!item.children || item.children.length === 0) &&
        originalItem.children
      ) {
        return {
          ...item,
          children: originalItem.children,
        };
      }
      return item;
    });
    setTreeData(expandedFilteredData);
    // 自动展开所有包含匹配结果的一级节点
    const keysToExpand: React.Key[] = [];
    expandedFilteredData.forEach((item: any) => {
      // 展开一级菜单匹配的节点
      if (item.title.toLowerCase().includes(value.toLowerCase())) {
        keysToExpand.push(item.key);
      }
      // 展开包含匹配子节点的一级节点
      if (item.children && item.children.length > 0) {
        keysToExpand.push(item.key);
      }
    });
    setExpandedKeys(keysToExpand);
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
    <div
      className={treeStyle.treeSelector}
      style={{
        ...style,
        minWidth: style.width,
      }}
    >
      <Spin spinning={loading}>
        <Search
          className="mb-[10px]"
          style={inputStyle}
          placeholder={t('common.searchPlaceHolder')}
          value={treeSearchValue}
          enterButton
          onChange={(e) => setTreeSearchValue(e.target.value)}
          onSearch={handleSearchTree}
        />
        {treeData.length ? (
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
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Spin>
    </div>
  );
};

export default TreeComponent;
