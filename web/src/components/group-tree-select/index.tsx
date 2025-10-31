import React, { useMemo, useCallback, useEffect, useState } from 'react';
import { Tag, Dropdown } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useUserInfoContext } from '@/context/userInfo';
import { convertGroupTreeToTreeSelectData } from '@/utils/index';
import { createStrategy } from './strategies';
import MultiCascadePanel from '@/components/multi-cascade-panel';
import type { GroupTreeSelectProps } from './types';
import type { CascadeNode } from '@/components/multi-cascade-panel';

const GroupTreeSelect: React.FC<GroupTreeSelectProps> = ({
  value = [],
  onChange,
  placeholder,
  multiple = true,
  disabled = false,
  style = { width: '100%' },
  mode = 'ownership',
  height = 300,
  showSearch = false,
}) => {
  const { groupTree } = useUserInfoContext();
  const [internalValue, setInternalValue] = useState<number[]>([]);
  const [open, setOpen] = useState(false);

  const treeSelectData = useMemo(() => {
    return convertGroupTreeToTreeSelectData(groupTree);
  }, [groupTree]);

  const processedTreeData = useMemo(() => {
    const strategy = createStrategy(mode);
    return strategy.transformTreeData(treeSelectData);
  }, [treeSelectData, mode]);

  const cascadeData = useMemo((): CascadeNode[] => {
    const convertToCascadeNode = (nodes: any[]): CascadeNode[] => {
      return nodes.map(node => ({
        value: node.value,
        label: node.title,
        disabled: node.disabled,
        children: node.children ? convertToCascadeNode(node.children) : undefined
      }));
    };
    return convertToCascadeNode(processedTreeData);
  }, [processedTreeData]);

  const getNodePath = useCallback((treeData: any[], targetId: number, path: string[] = []): string[] => {
    for (const item of treeData) {
      const currentPath = [...path, item.title];

      if (item.value === targetId) {
        return currentPath;
      }

      if (item.children) {
        const found = getNodePath(item.children, targetId, currentPath);
        if (found.length > 0) {
          return found;
        }
      }
    }
    return [];
  }, []);

  // 新增：根据ID获取完整路径标签（如 "总公司 / A分公司"）
  const getFullPathLabel = useCallback((treeData: any[], targetId: number): string => {
    const pathArray = getNodePath(treeData, targetId);
    return pathArray.length > 0 ? pathArray.join(' / ') : targetId.toString();
  }, [getNodePath]);

  // Validate if the target ID exists in the tree data
  const isValidValue = useCallback((targetId: number): boolean => {
    const checkNode = (nodes: any[]): boolean => {
      return nodes.some(node =>
        node.value === targetId || (node.children && checkNode(node.children))
      );
    };
    return checkNode(processedTreeData);
  }, [processedTreeData]);

  // Convert any value to number array safely
  const normalizeValue = useCallback((val: any): number[] => {
    if (!val) return [];
    if (Array.isArray(val)) {
      return val.filter(id => id != null && !isNaN(Number(id))).map(Number);
    }
    const numVal = Number(val);
    return !isNaN(numVal) ? [numVal] : [];
  }, []);

  const valueString = useMemo(() => JSON.stringify(value), [value]);

  useEffect(() => {
    if (!processedTreeData.length) return;

    const normalizedValue = normalizeValue(value);
    const validValues = normalizedValue.filter(id => isValidValue(id));

    // Update internal state only when value actually changes
    const currentValueString = JSON.stringify(internalValue);
    const newValueString = JSON.stringify(validValues);

    if (currentValueString !== newValueString) {
      setInternalValue(validValues);
    }
  }, [valueString, processedTreeData, isValidValue, normalizeValue]);

  // 处理 MultiCascadePanel 值变化
  const handlePanelChange = useCallback((newValue: number[]) => {
    setInternalValue(newValue);
    if (multiple) {
      onChange?.(newValue);
    } else {
      // 单选模式：传递单个值或第一个值
      onChange?.(newValue.length > 0 ? newValue[0] : undefined);
    }
  }, [onChange, multiple]);

  const handleRemoveTag = useCallback((removedId: number) => {
    const newValue = internalValue.filter(id => id !== removedId);
    setInternalValue(newValue);
    onChange?.(newValue);
  }, [internalValue, onChange]);

  const dropdownContent = (
    <div
      className="bg-white rounded shadow-lg"
      onClick={(e) => e.stopPropagation()}
    >
      <MultiCascadePanel
        data={cascadeData}
        value={internalValue}
        onChange={handlePanelChange}
        cascade={false}
        height={height}
        columnWidth={200}
        disabled={disabled}
        searchable={showSearch}
        searchPlaceholder={placeholder}
        single={!multiple}
      />
    </div>
  );

  const displayContent = useMemo(() => {
    if (internalValue.length === 0) {
      return <span className="text-gray-400">{placeholder || '请选择'}</span>;
    }
    if (multiple) {
      return (
        <div className="flex flex-wrap gap-1">
          {internalValue.map(id => (
            <Tag
              key={id}
              closable={!disabled}
              onClose={(e) => {
                e.stopPropagation();
                handleRemoveTag(id);
              }}
            >
              {getFullPathLabel(processedTreeData, id)}
            </Tag>
          ))}
        </div>
      );
    }
    return getFullPathLabel(processedTreeData, internalValue[0]);
  }, [internalValue, multiple, disabled, placeholder, processedTreeData, getFullPathLabel, handleRemoveTag]);

  return (
    <div style={style}>
      <Dropdown
        open={open}
        onOpenChange={setOpen}
        trigger={['click']}
        disabled={disabled}
        dropdownRender={() => dropdownContent}
        placement="bottomLeft"
      >
        <div
          className={`
            px-3 py-1 border rounded min-h-8
            flex items-center justify-between w-full
            ${disabled ? 'cursor-not-allowed bg-gray-100' : 'cursor-pointer bg-white'}
          `}
          style={{ borderColor: 'var(--color-border)' }}
        >
          <div className="flex-1 overflow-hidden">
            {displayContent}
          </div>
          <DownOutlined className="text-xs text-gray-400 ml-2" />
        </div>
      </Dropdown>
    </div>
  );
};

export default GroupTreeSelect;
