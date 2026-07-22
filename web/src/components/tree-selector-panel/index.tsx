import React, { useEffect, useMemo, useState } from 'react';
import { Input, Spin, Tree } from 'antd';
import type { CSSProperties, Key, ReactNode } from 'react';
import type { TreeDataNode, TreeProps } from 'antd';
import { cloneDeep } from 'lodash';
import CompactEmptyState from '@/components/compact-empty-state';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';

const { Search } = Input;

export interface TreeSelectorPanelItem {
  title: ReactNode;
  key: string | number;
  label?: string;
  icon?: string;
  count?: number;
  children: TreeSelectorPanelItem[];
}

export interface TreeSelectorPanelProps<TSortData = unknown> {
  data: TreeSelectorPanelItem[];
  defaultSelectedKey?: Key;
  loading?: boolean;
  draggable?: boolean;
  showAllMenu?: boolean;
  surface?: 'plain' | 'panel';
  style?: CSSProperties;
  inputStyle?: CSSProperties;
  onNodeSelect?: (key: string) => void;
  buildSortPayload?: (nodes: TreeSelectorPanelItem[]) => TSortData[];
  onNodeDrag?: (sortNodes: TSortData[], nodes: TreeDataNode[]) => void;
}

const toSearchableText = (value: ReactNode) => {
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }

  return '';
};

const renderDefaultTitle = (item: TreeSelectorPanelItem) => {
  const hasMeta = Boolean(item.icon) || item.count != null;

  if (!hasMeta) {
    return <span>{item.title}</span>;
  }

  return (
    <span className={`${styles.node} treeMetaNode`}>
      {item.icon ? (
        <span className={styles.icon}>
          <img
            className={styles.iconImage}
            src={`/assets/icons/${item.icon}.svg`}
            alt={typeof item.title === 'string' ? item.title : 'icon'}
            onError={(event) => {
              (event.target as HTMLImageElement).src =
                '/assets/icons/cc-default_默认.svg';
            }}
          />
        </span>
      ) : null}
      <span className={styles.label}>
        {typeof item.title === 'string' ? (
          <EllipsisWithTooltip className={styles.ellipsis} text={item.title} />
        ) : (
          item.title
        )}
      </span>
      {item.count != null ? (
        <span className={styles.count}>{item.count}</span>
      ) : null}
    </span>
  );
};

function TreeSelectorPanel<TSortData = unknown>({
  data,
  defaultSelectedKey,
  loading = false,
  draggable = false,
  showAllMenu = false,
  surface = 'plain',
  style,
  inputStyle,
  onNodeSelect,
  buildSortPayload,
  onNodeDrag,
}: TreeSelectorPanelProps<TSortData>) {
  const { t } = useTranslation();
  const [selectedKeys, setSelectedKeys] = useState<Key[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<Key[]>([]);
  const [treeSearchValue, setTreeSearchValue] = useState('');
  const [originalTreeData, setOriginalTreeData] = useState<TreeSelectorPanelItem[]>([]);
  const [treeData, setTreeData] = useState<TreeSelectorPanelItem[]>([]);

  useEffect(() => {
    if (defaultSelectedKey !== undefined && defaultSelectedKey !== null) {
      setSelectedKeys([defaultSelectedKey]);
      onNodeSelect?.(String(defaultSelectedKey));
    }
  }, [defaultSelectedKey, onNodeSelect]);

  useEffect(() => {
    setOriginalTreeData(data);
    const filteredData = filterAllMenu(data);
    setTreeData(filteredData);
    setExpandedKeys(filteredData.map((item) => item.key));
  }, [data, showAllMenu]);

  const resolvedStyle = useMemo(() => {
    if (style?.width == null) {
      return style;
    }

    return {
      ...style,
      minWidth: style.width,
    };
  }, [style]);

  const filterAllMenu = (
    currentData: TreeSelectorPanelItem[],
    searchValue = '',
  ) => {
    if (!showAllMenu || searchValue) {
      return currentData.filter((item) => item.key !== 'all');
    }

    return currentData;
  };

  const filterTree = (
    currentData: TreeSelectorPanelItem[],
    searchValue: string,
  ): TreeSelectorPanelItem[] => {
    return currentData
      .map((item) => {
        const children = filterTree(item.children || [], searchValue);
        const searchableText = toSearchableText(item.title).toLowerCase();

        if (
          searchableText.includes(searchValue.toLowerCase()) ||
          children.length
        ) {
          return {
            ...item,
            children,
          };
        }

        return null;
      })
      .filter(Boolean) as TreeSelectorPanelItem[];
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
    const expandedFilteredData = allMenuFilteredData.map((item) => {
      const originalItem = originalTreeData.find((origin) => origin.key === item.key);

      if (
        originalItem &&
        toSearchableText(item.title).toLowerCase().includes(value.toLowerCase()) &&
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

    const keysToExpand: Key[] = [];
    expandedFilteredData.forEach((item) => {
      if (toSearchableText(item.title).toLowerCase().includes(value.toLowerCase())) {
        keysToExpand.push(item.key);
      }

      if (item.children && item.children.length > 0) {
        keysToExpand.push(item.key);
      }
    });

    setExpandedKeys(keysToExpand);
  };

  const handleSelect = (nextSelectedKeys: Key[], info: any) => {
    const isFirstLevel = Boolean(info.node?.children?.length);

    if (!isFirstLevel && nextSelectedKeys.length) {
      setSelectedKeys(nextSelectedKeys);
      onNodeSelect?.(String(nextSelectedKeys[0]));
    }
  };

  const onDrop: TreeProps['onDrop'] = (info) => {
    const { dragNode, node: dropNode } = info;
    const dropKey = dropNode.key;
    const dragKey = dragNode.key;
    const dropPos = dropNode.pos.split('-');
    const dragPos = dragNode.pos.split('-');
    const dropLevel = dropPos.length;
    const dragLevel = dragPos.length;
    const dropPosition =
      info.dropPosition - Number(dropPos[dropPos.length - 1]);
    const nextData = cloneDeep(data);

    if (dragLevel === 2) {
      if (
        dropNode.dragOverGapTop ||
        dropLevel === 2 ||
        dropNode.dragOverGapBottom
      ) {
        const targetKey = dropNode.dragOverGapBottom
          ? dropKey
          : dropKey;
        const draggingIndex = nextData.findIndex((item) => item.key === dragKey);
        const targetIndex = nextData.findIndex((item) => item.key === targetKey);

        if (draggingIndex === -1 || targetIndex === -1) {
          return;
        }

        const [draggedItem] = nextData.splice(draggingIndex, 1);
        const insertIndex = dropNode.dragOverGapBottom ? targetIndex + 1 : targetIndex;
        const adjustedIndex =
          draggingIndex < insertIndex ? insertIndex - 1 : insertIndex;

        nextData.splice(adjustedIndex, 0, draggedItem);
        onNodeDrag?.(buildSortPayload?.(nextData as TreeSelectorPanelItem[]) || [], nextData);
      }

      return;
    }

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
      nodes: TreeDataNode[],
      key: Key,
      callback: (node: TreeDataNode, index: number, list: TreeDataNode[]) => void,
    ) => {
      for (let index = 0; index < nodes.length; index += 1) {
        if (nodes[index].key === key) {
          return callback(nodes[index], index, nodes);
        }

        if (nodes[index].children) {
          loop(nodes[index].children!, key, callback);
        }
      }
    };

    let dragObj: TreeDataNode;

    loop(nextData, dragKey, (item, index, list) => {
      list.splice(index, 1);
      dragObj = item;
    });

    if (!info.dropToGap) {
      loop(nextData, dropKey, (item) => {
        item.children = item.children || [];
        item.children.unshift(dragObj);
      });
    } else {
      let currentList: TreeDataNode[] = [];
      let currentIndex = 0;

      loop(nextData, dropKey, (_item, index, list) => {
        currentList = list;
        currentIndex = index;
      });

      if (dropPosition === -1) {
        currentList.splice(currentIndex, 0, dragObj!);
      } else {
        currentList.splice(currentIndex + 1, 0, dragObj!);
      }
    }

    onNodeDrag?.(
      buildSortPayload?.(nextData as TreeSelectorPanelItem[]) || [],
      nextData,
    );
  };

  return (
    <div
      className={surface === 'panel' ? styles.panel : 'h-full'}
      style={resolvedStyle}
    >
      <Spin spinning={loading}>
        <Search
          className="mb-[10px]"
          style={inputStyle}
          placeholder={t('common.searchPlaceHolder')}
          value={treeSearchValue}
          enterButton
          onChange={(event) => setTreeSearchValue(event.target.value)}
          onSearch={handleSearchTree}
        />
        {treeData.length ? (
          <div className={styles.treeWrap}>
            <Tree
              showLine
              draggable={draggable}
              selectedKeys={selectedKeys}
              expandedKeys={expandedKeys}
              treeData={treeData}
              titleRender={(node) =>
                renderDefaultTitle(node as unknown as TreeSelectorPanelItem)
              }
              onExpand={(keys) => setExpandedKeys(keys)}
              onSelect={handleSelect}
              onDrop={onDrop}
            />
          </div>
        ) : (
          <CompactEmptyState description={t('common.noData')} className="py-6" />
        )}
      </Spin>
    </div>
  );
}

export default TreeSelectorPanel;
