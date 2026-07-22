'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Input } from 'antd';
import { HolderOutlined, PlusOutlined, MinusOutlined } from '@ant-design/icons';
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import OperateFormModal from '@/components/operate-form-modal';
import { useTranslation } from '@/utils/i18n';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import type { FilterOption } from '@/app/ops-analysis/components/ops-analysis-widgets';

interface FilterOptionsModalProps {
  open: boolean;
  options: FilterOption[];
  onCancel: () => void;
  onConfirm: (options: FilterOption[]) => void;
}

interface SortableOptionRowProps {
  id: string;
  option: FilterOption;
  onChange: (id: string, field: keyof FilterOption, value: string) => void;
  onAddAfter: (id: string) => void;
  onRemove: (id: string) => void;
  showRemove: boolean;
}

interface EditableOption extends FilterOption {
  id: string;
}

const createEmptyOption = (): EditableOption => ({
  id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  label: '',
  value: '',
});

const SortableOptionRow: React.FC<SortableOptionRowProps> = ({
  id,
  option,
  onChange,
  onAddAfter,
  onRemove,
  showRemove,
}) => {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <li ref={setNodeRef} style={style} className="flex items-center mb-2">
      <HolderOutlined
        {...attributes}
        {...listeners}
        className="mr-[4px] cursor-grab text-[var(--color-text-3)]"
      />
      <Input
        placeholder={option.value ? undefined : '请输入选项ID'}
        className="mr-[10px] w-2/5"
        value={option.value}
        onChange={(e) => onChange(id, 'value', e.target.value)}
      />
      <Input
        placeholder={option.label ? undefined : '请输入选项名称'}
        className="mr-[10px] w-2/5"
        value={option.label}
        onChange={(e) => onChange(id, 'label', e.target.value)}
      />
      <PlusOutlined
        className="mr-[10px] cursor-pointer text-[var(--color-primary)]"
        onClick={() => onAddAfter(id)}
      />
      {showRemove && (
        <MinusOutlined
          className="cursor-pointer text-[var(--color-primary)]"
          onClick={() => onRemove(id)}
        />
      )}
    </li>
  );
};

const FilterOptionsModal: React.FC<FilterOptionsModalProps> = ({
  open,
  options: initialOptions,
  onCancel,
  onConfirm,
}) => {
  const { t } = useTranslation();
  const guardClose = useUnsavedConfirm();
  const [options, setOptions] = useState<EditableOption[]>([]);
  const hasInitializedRef = useRef(false);

  const isDirty = () => {
    const normalize = (list: FilterOption[]) =>
      JSON.stringify(
        list
          .map(({ label, value }) => ({
            label: (label || '').trim(),
            value: (value || '').trim(),
          }))
          .filter((item) => item.label || item.value),
      );
    return normalize(options) !== normalize(initialOptions);
  };

  const handleCancel = () => guardClose(isDirty(), onCancel);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  useEffect(() => {
    if (!open) {
      hasInitializedRef.current = false;
      return;
    }

    if (hasInitializedRef.current) return;
    hasInitializedRef.current = true;

    setOptions(
      initialOptions.length > 0
        ? initialOptions.map((item) => ({
          ...item,
          id: createEmptyOption().id,
        }))
        : [createEmptyOption()],
    );
  }, [open, initialOptions]);

  const optionIds = useMemo(() => options.map((item) => item.id), [options]);

  const handleOptionChange = (
    id: string,
    field: keyof FilterOption,
    value: string,
  ) => {
    setOptions((prev) =>
      prev.map((item) => (item.id === id ? { ...item, [field]: value } : item)),
    );
  };

  const handleAddAfter = (id: string) => {
    setOptions((prev) => {
      const index = prev.findIndex((item) => item.id === id);
      const next = [...prev];
      next.splice(index + 1, 0, createEmptyOption());
      return next;
    });
  };

  const handleRemove = (id: string) => {
    setOptions((prev) => {
      const next = prev.filter((item) => item.id !== id);
      return next.length > 0 ? next : [createEmptyOption()];
    });
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) {
      return;
    }

    setOptions((prev) => {
      const oldIndex = prev.findIndex((item) => item.id === active.id);
      const newIndex = prev.findIndex((item) => item.id === over.id);
      return arrayMove(prev, oldIndex, newIndex);
    });
  };

  const handleConfirm = () => {
    onConfirm(
      options
        .filter((item) => item.label.trim() && item.value.trim())
        .map(({ label, value }) => ({
          label: label.trim(),
          value: value.trim(),
        })),
    );
  };

  return (
    <OperateFormModal
      title={t('dashboard.configOptions')}
      open={open}
      onCancel={handleCancel}
      onConfirm={handleConfirm}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      width={560}
      maskClosable={false}
      centered
      destroyOnHidden
    >
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={optionIds}
          strategy={verticalListSortingStrategy}
        >
          <ul className="pt-2">
            <li className="mb-2 flex items-center text-sm text-[var(--color-text-2)]">
              <span className="mr-[4px] w-[14px]" />
              <span className="mr-[10px] w-2/5">
                {t('dashboard.optionValue')}
              </span>
              <span className="mr-[10px] w-2/5">
                {t('dashboard.optionLabel')}
              </span>
            </li>
            {options.map((option) => (
              <SortableOptionRow
                key={option.id}
                id={option.id}
                option={option}
                onChange={handleOptionChange}
                onAddAfter={handleAddAfter}
                onRemove={handleRemove}
                showRemove={options.length > 1}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </OperateFormModal>
  );
};

export default FilterOptionsModal;
