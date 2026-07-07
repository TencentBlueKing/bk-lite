import React, { useMemo, useCallback, useEffect, useState } from 'react';
import { Tag, Dropdown } from 'antd';
import { CloseCircleFilled, DownOutlined } from '@ant-design/icons';
import { useUserInfoContext } from '@/context/userInfo';
import { convertGroupTreeToTreeSelectData } from '@/utils/index';
import { createStrategy } from './strategies';
import MultiCascadePanel from '@/components/multi-cascade-panel';
import type { GroupTreeSelectProps } from './types';
import type { CascadeNode } from '@/components/multi-cascade-panel';
import { useTranslation } from '@/utils/i18n';

const GroupTreeSelect: React.FC<GroupTreeSelectProps> = ({
  value = [],
  onChange,
  placeholder,
  multiple = true,
  disabled = false,
  allowClear = false,
  style = { width: '100%' },
  mode = 'ownership',
  height = 300,
  showSearch = false,
  filterByRootId,
  lockedValues = [],
}) => {
  const { groupTree } = useUserInfoContext();
  const { t } = useTranslation();
  const [internalValue, setInternalValue] = useState<number[]>([]);
  const [open, setOpen] = useState(false);

  // 锁定项（如「管理组织」自动并入「使用组织」）：始终被选中、不可取消
  const lockedString = useMemo(() => JSON.stringify(lockedValues || []), [lockedValues]);
  const lockedIds = useMemo<number[]>(() => (lockedValues || []).map(Number).filter((n) => !Number.isNaN(n)), [lockedString]);
  const lockedSet = useMemo(() => new Set<number>(lockedIds), [lockedIds]);

  const treeSelectData = useMemo(() => {
    return convertGroupTreeToTreeSelectData(groupTree);
  }, [groupTree]);

  // 根据 filterByRootId 过滤树数据
  const filteredTreeData = useMemo(() => {
    if (!filterByRootId) return treeSelectData;

    const findSubTree = (nodes: any[], targetId: number): any | null => {
      for (const node of nodes) {
        if (node.value === targetId) {
          return node;
        }
        if (node.children) {
          const found = findSubTree(node.children, targetId);
          if (found) return found;
        }
      }
      return null;
    };

    const targetNode = findSubTree(treeSelectData, filterByRootId);
    return targetNode ? [targetNode] : [];
  }, [treeSelectData, filterByRootId]);

  const processedTreeData = useMemo(() => {
    const strategy = createStrategy(mode);
    return strategy.transformTreeData(filteredTreeData);
  }, [filteredTreeData, mode]);

  const cascadeData = useMemo((): CascadeNode[] => {
    const convertToCascadeNode = (nodes: any[]): CascadeNode[] => {
      return nodes.map(node => ({
        value: node.value,
        label: node.title,
        // 锁定项在面板中置灰（已勾选且不可取消）
        disabled: node.disabled || lockedSet.has(node.value),
        children: node.children ? convertToCascadeNode(node.children) : undefined
      }));
    };
    return convertToCascadeNode(processedTreeData);
  }, [processedTreeData, lockedSet]);

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
    // 锁定项始终保留（即便外部 value 暂未包含），且仅保留树中有效的锁定项
    const withLocked = Array.from(new Set([...validValues, ...lockedIds.filter(id => isValidValue(id))]));

    // Update internal state only when value actually changes
    const currentValueString = JSON.stringify(internalValue);
    const newValueString = JSON.stringify(withLocked);

    if (currentValueString !== newValueString) {
      setInternalValue(withLocked);
    }
  }, [valueString, processedTreeData, isValidValue, normalizeValue, lockedIds]);

  // 处理 MultiCascadePanel 值变化
  const handlePanelChange = useCallback((newValue: number[]) => {
    // 锁定项不可移除：始终并入（即便面板尝试取消也会被补回）
    const merged = Array.from(new Set([...newValue, ...lockedIds]));
    setInternalValue(merged);
    if (multiple) {
      onChange?.(merged);
    } else {
      // 单选模式：传递单个值或第一个值
      onChange?.(merged.length > 0 ? merged[0] : undefined);
    }
  }, [onChange, multiple, lockedIds]);

  const handleRemoveTag = useCallback((removedId: number) => {
    if (lockedSet.has(removedId)) return; // 锁定项不可删除
    const newValue = internalValue.filter(id => id !== removedId);
    setInternalValue(newValue);
    onChange?.(newValue);
  }, [internalValue, onChange, lockedSet]);

  const handleClear = useCallback((event: React.MouseEvent) => {
    event.stopPropagation();
    // 清空时保留锁定项（锁定项不可被清除）
    const cleared = Array.from(lockedSet) as number[];
    setInternalValue(cleared);
    onChange?.(multiple ? cleared : (cleared.length > 0 ? cleared[0] : undefined));
  }, [multiple, onChange, lockedSet]);

  const dropdownContent = (
    <div
      className="rounded shadow-lg"
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
      return <span className="text-(--ant-color-text-placeholder)">{placeholder || t('common.pleaseSelect')}</span>;
    }
    if (multiple) {
      return (
        <div className="flex flex-wrap gap-1">
          {internalValue.map(id => (
            <Tag
              key={id}
              closable={!disabled && !lockedSet.has(id)}
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
  }, [internalValue, multiple, disabled, placeholder, processedTreeData, getFullPathLabel, handleRemoveTag, lockedSet]);

  return (
    <div style={style}>
      <Dropdown
        open={open}
        onOpenChange={setOpen}
        trigger={['click']}
        disabled={disabled}
        popupRender={() => dropdownContent}
        placement="bottomLeft"
      >
        <div
          className={`
            px-3 py-1 border rounded min-h-8
            flex items-center justify-between w-full
            ${disabled ? 'cursor-not-allowed bg-(--ant-color-bg-container-disabled)' : 'cursor-pointer bg-[var(--color-bg)]'}
          `}
          style={{ borderColor: 'var(--color-border)' }}
        >
          <div className="flex-1 overflow-hidden">
            {displayContent}
          </div>
          {allowClear && internalValue.length > 0 && !disabled && (
            <CloseCircleFilled
              className="text-xs text-gray-400 ml-2 hover:text-gray-500"
              onClick={handleClear}
            />
          )}
          <DownOutlined className="text-xs text-gray-400 ml-2" />
        </div>
      </Dropdown>
    </div>
  );
};

export default GroupTreeSelect;
