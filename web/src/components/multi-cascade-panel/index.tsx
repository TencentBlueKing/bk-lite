/**
 * MultiCascadePanel 组件
 * 参考 RSuite MultiCascader 设计，实现多列级联面板，支持独立选择模式
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { Checkbox, Input } from 'antd';
import { RightOutlined, SearchOutlined } from '@ant-design/icons';
import type { CheckboxChangeEvent } from 'antd/lib/checkbox';

export interface CascadeNode {
  value: number;
  label: string;
  children?: CascadeNode[];
  disabled?: boolean;
  [key: string]: any;
}

export interface MultiCascadePanelProps {
  /**
   * 数据源
   */
  data: CascadeNode[];

  /**
   * 当前选中的值
   */
  value?: number[];

  /**
   * 值变化回调
   */
  onChange?: (value: number[]) => void;

  /**
   * 是否级联选择
   * @default false
   */
  cascade?: boolean;

  /**
   * 面板高度
   * @default 300
   */
  height?: number;

  /**
   * 列宽度
   * @default 200
   */
  columnWidth?: number;

  /**
   * 是否禁用
   * @default false
   */
  disabled?: boolean;

  /**
   * 是否显示搜索框
   * @default false
   */
  searchable?: boolean;

  /**
   * 搜索占位符
   */
  searchPlaceholder?: string;

  /**
   * 是否单选模式
   * @default false
   */
  single?: boolean;
}

interface ColumnItem {
  level: number;
  nodes: CascadeNode[];
  parentValue?: number;
}

const MultiCascadePanel: React.FC<MultiCascadePanelProps> = ({
  data,
  value = [],
  onChange,
  cascade = false,
  height = 300,
  columnWidth = 200,
  disabled = false,
  searchable = false,
  searchPlaceholder = '搜索...',
  single = false,
}) => {
  const [selectedValue, setSelectedValue] = useState<number[]>(value);
  const [activeNode, setActiveNode] = useState<number | null>(null);
  const [searchText, setSearchText] = useState('');
  const [columns, setColumns] = useState<ColumnItem[]>([
    { level: 0, nodes: data }
  ]);

  useEffect(() => {
    setSelectedValue(value);
  }, [value]);

  useEffect(() => {
    setColumns([{ level: 0, nodes: data }]);
  }, [data]);

  const findNode = useCallback((nodes: CascadeNode[], targetValue: number): CascadeNode | null => {
    for (const node of nodes) {
      if (node.value === targetValue) {
        return node;
      }
      if (node.children) {
        const found = findNode(node.children, targetValue);
        if (found) return found;
      }
    }
    return null;
  }, []);

  const getAllChildrenValues = useCallback((node: CascadeNode): number[] => {
    const values: number[] = [];

    const traverse = (n: CascadeNode) => {
      values.push(n.value);
      if (n.children) {
        n.children.forEach(child => traverse(child));
      }
    };

    if (node.children) {
      node.children.forEach(child => traverse(child));
    }

    return values;
  }, []);

  const handleCheckboxChange = useCallback((node: CascadeNode, checked: boolean) => {
    if (disabled) return;

    let newValue: number[] = [...selectedValue];

    if (single) {
      // 单选模式：直接替换为当前节点
      newValue = [node.value];
    } else if (cascade) {
      const childrenValues = getAllChildrenValues(node);

      if (checked) {
        newValue.push(node.value, ...childrenValues);
        newValue = [...new Set(newValue)];
      } else {
        const valuesToRemove = new Set([node.value, ...childrenValues]);
        newValue = newValue.filter(v => !valuesToRemove.has(v));
      }
    } else {
      if (checked) {
        newValue.push(node.value);
      } else {
        newValue = newValue.filter(v => v !== node.value);
      }
    }

    setSelectedValue(newValue);
    onChange?.(newValue);
  }, [selectedValue, cascade, disabled, onChange, getAllChildrenValues, single]);

  // 处理节点鼠标悬停（展开下一列）
  const handleNodeHover = useCallback((node: CascadeNode, level: number) => {
    if (disabled) return;

    setActiveNode(node.value);

    if (node.children && node.children.length > 0) {
      const newColumns = columns.slice(0, level + 1);
      newColumns.push({
        level: level + 1,
        nodes: node.children,
        parentValue: node.value
      });
      setColumns(newColumns);
    } else {
      setColumns(columns.slice(0, level + 1));
    }
  }, [columns, disabled]);

  // 处理节点点击（用于多选模式的展开）
  const handleNodeClick = useCallback((node: CascadeNode, level: number) => {
    if (disabled) return;

    // 单选模式下，点击直接选择
    if (single && !node.disabled) {
      handleCheckboxChange(node, true);
      return;
    }

    // 多选模式下，点击展开子级
    setActiveNode(node.value);

    if (node.children && node.children.length > 0) {
      const newColumns = columns.slice(0, level + 1);
      newColumns.push({
        level: level + 1,
        nodes: node.children,
        parentValue: node.value
      });
      setColumns(newColumns);
    } else {
      setColumns(columns.slice(0, level + 1));
    }
  }, [columns, disabled, single, handleCheckboxChange]);

  const isNodeChecked = useCallback((node: CascadeNode): boolean => {
    return selectedValue.includes(node.value);
  }, [selectedValue]);

  const isNodeIndeterminate = useCallback((node: CascadeNode): boolean => {
    if (!node.children || node.children.length === 0) return false;

    const childrenValues = getAllChildrenValues(node);
    const selectedCount = childrenValues.filter(v => selectedValue.includes(v)).length;

    return selectedCount > 0 && selectedCount < childrenValues.length;
  }, [selectedValue, getAllChildrenValues]);

  // 过滤节点（搜索）
  const filterNodes = useCallback((nodes: CascadeNode[], text: string): CascadeNode[] => {
    if (!text) return nodes;

    return nodes.filter(node => {
      const match = node.label.toLowerCase().includes(text.toLowerCase());
      const childMatch = node.children ? filterNodes(node.children, text).length > 0 : false;
      return match || childMatch;
    }).map(node => ({
      ...node,
      children: node.children ? filterNodes(node.children, text) : undefined
    }));
  }, []);

  // 应用搜索过滤
  const filteredColumns = useMemo(() => {
    if (!searchText) return columns;

    return columns.map(col => ({
      ...col,
      nodes: filterNodes(col.nodes, searchText)
    }));
  }, [columns, searchText, filterNodes]);

  // 渲染单个节点
  const renderNode = useCallback((node: CascadeNode, level: number) => {
    const isChecked = isNodeChecked(node);
    const isIndeterminate = cascade && isNodeIndeterminate(node);
    const isActive = activeNode === node.value;
    const hasChildren = node.children && node.children.length > 0;

    return (
      <div
        key={node.value}
        className={`
          flex items-center justify-between px-3 py-2 cursor-pointer
          transition-colors duration-200
          hover:bg-[var(--color-fill-2)]
          ${isActive ? 'bg-[var(--color-fill-2)]' : ''}
          ${isChecked && single ? 'bg-[var(--color-primary-light-1)]' : ''}
          ${node.disabled ? 'cursor-not-allowed opacity-50' : ''}
        `}
        onClick={() => handleNodeClick(node, level)}
        onMouseEnter={() => single ? handleNodeHover(node, level) : undefined}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {!single && (
            <Checkbox
              checked={isChecked}
              indeterminate={isIndeterminate}
              disabled={disabled || node.disabled}
              onChange={(e: CheckboxChangeEvent) => {
                e.stopPropagation();
                handleCheckboxChange(node, e.target.checked);
              }}
              onClick={(e) => e.stopPropagation()}
            />
          )}
          <span className="truncate flex-1">{node.label}</span>
        </div>
        {hasChildren && (
          <RightOutlined className="text-[var(--color-text-3)] text-xs ml-2 flex-shrink-0" />
        )}
      </div>
    );
  }, [
    isNodeChecked,
    isNodeIndeterminate,
    activeNode,
    disabled,
    cascade,
    single,
    handleNodeClick,
    handleNodeHover,
    handleCheckboxChange
  ]);

  // 渲染单列
  const renderColumn = useCallback((column: ColumnItem) => {
    return (
      <div
        key={`column-${column.level}`}
        className="flex flex-col border-r border-[var(--color-border)] last:border-r-0"
        style={{
          width: columnWidth,
          height: '100%',
          flexShrink: 0
        }}
      >
        <div className="flex-1 overflow-auto">
          {column.nodes.length > 0 ? (
            column.nodes.map(node => renderNode(node, column.level))
          ) : (
            <div className="flex items-center justify-center h-full text-[var(--color-text-3)]">
              暂无数据
            </div>
          )}
        </div>
      </div>
    );
  }, [columnWidth, renderNode]);

  return (
    <div className="multi-cascade-panel">
      {searchable && (
        <div className="p-2 border-b border-[var(--color-border)]">
          <Input
            prefix={<SearchOutlined />}
            placeholder={searchPlaceholder}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
          />
        </div>
      )}

      <div
        className="flex overflow-x-auto border border-[var(--color-border)] rounded"
        style={{ height }}
      >
        {filteredColumns.map((column) => renderColumn(column))}
      </div>
    </div>
  );
};

export default MultiCascadePanel;
