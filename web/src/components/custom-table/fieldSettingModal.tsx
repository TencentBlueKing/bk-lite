import React, { useMemo, useState, forwardRef, useImperativeHandle } from 'react';
import { Checkbox, Button, Input, Tooltip } from 'antd';
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import type { CheckboxProps } from 'antd';
import fieldSettingModalStyle from './index.module.scss';
import {
  HolderOutlined,
  CloseOutlined,
  PushpinOutlined,
  PushpinFilled,
} from '@ant-design/icons';
import { cloneDeep } from 'lodash';
import { ColumnItem, GroupFieldItem } from '@/types/index';

interface SortableFieldItemProps {
  field: ColumnItem;
  pinned: boolean;
  enableFixedFields: boolean;
  onRemove: (key: string) => void;
  onTogglePin: (key: string) => void;
}

interface FieldModalProps {
  onConfirm: (
    fieldKeys: string[],
    fixedFieldKeys?: string[]
  ) => void | Promise<void>;
  choosableFields: ColumnItem[];
  displayFieldKeys: string[];
  fixedFieldKeys?: string[];
  defaultFixedFieldKeys?: string[];
  enableFixedFields?: boolean;
  groupFields?: GroupFieldItem[];
  searchable?: boolean;
  width?: number;
}

export interface FieldModalRef {
  showModal: () => void;
}

const orderWithPinnedFirst = (
  fields: ColumnItem[],
  pinnedKeys: string[]
): ColumnItem[] => {
  const pinnedSet = new Set(pinnedKeys);
  const pinned = fields.filter((field) => pinnedSet.has(field.key));
  const rest = fields.filter((field) => !pinnedSet.has(field.key));
  return [...pinned, ...rest];
};

const SortableFieldItem = ({
  field,
  pinned,
  enableFixedFields,
  onRemove,
  onTogglePin,
}: SortableFieldItemProps) => {
  const { t } = useTranslation();
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: field.key,
    transition: {
      duration: 220,
      easing: 'cubic-bezier(0.2, 0, 0, 1)',
    },
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`${fieldSettingModalStyle.fieldItem} ${
        isDragging ? fieldSettingModalStyle.draggingItem : ''
      } ${pinned ? fieldSettingModalStyle.pinnedItem : ''}`}
    >
      <HolderOutlined
        {...attributes}
        {...listeners}
        aria-label={field.title}
        className={fieldSettingModalStyle.dragTrigger}
      />
      <span className={fieldSettingModalStyle.dragLabel} title={field.title}>
        {field.title}
      </span>
      <span className={fieldSettingModalStyle.fieldActions}>
        {enableFixedFields && (
          <Tooltip title={pinned ? t('common.unpin') : t('common.pin')}>
            <button
              type="button"
              className={`${fieldSettingModalStyle.pinItem} ${
                pinned ? fieldSettingModalStyle.pinItemActive : ''
              }`}
              aria-label={pinned ? t('common.unpin') : t('common.pin')}
              onClick={() => onTogglePin(field.key)}
            >
              {pinned ? <PushpinFilled /> : <PushpinOutlined />}
            </button>
          </Tooltip>
        )}
        <CloseOutlined
          aria-label={field.title}
          className={fieldSettingModalStyle.clearItem}
          onClick={() => onRemove(field.key)}
        />
      </span>
    </div>
  );
};

const FieldDragOverlay = ({
  field,
  pinned,
  enableFixedFields,
}: {
  field: ColumnItem;
  pinned: boolean;
  enableFixedFields: boolean;
}) => (
  <div aria-hidden="true" className={fieldSettingModalStyle.dragOverlay}>
    <HolderOutlined className={fieldSettingModalStyle.dragTrigger} />
    <span className={fieldSettingModalStyle.dragLabel}>{field.title}</span>
    {enableFixedFields && (
      <span className={fieldSettingModalStyle.fieldActions}>
        {pinned ? <PushpinFilled /> : <PushpinOutlined />}
      </span>
    )}
  </div>
);

const FieldSettingModal = forwardRef<FieldModalRef, FieldModalProps>(
  (
    {
      onConfirm,
      choosableFields,
      displayFieldKeys,
      fixedFieldKeys,
      defaultFixedFieldKeys = [],
      enableFixedFields = false,
      groupFields,
      searchable = false,
      width = 600,
    },
    ref
  ) => {
    const { t } = useTranslation();
    const [title, setTitle] = useState<string>('');
    const [visible, setVisible] = useState<boolean>(false);
    const [checkedFields, setCheckedFields] = useState<string[]>(
      choosableFields.map((field) => field.key)
    );
    const [dragFields, setDragFields] = useState<ColumnItem[]>([]);
    const [pinnedFields, setPinnedFields] = useState<string[]>([]);
    const [activeFieldKey, setActiveFieldKey] = useState<string | null>(null);
    const [searchText, setSearchText] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const sensors = useSensors(
      useSensor(PointerSensor, {
        activationConstraint: { distance: 5 },
      }),
      useSensor(KeyboardSensor, {
        coordinateGetter: sortableKeyboardCoordinates,
      })
    );
    const checkAll = choosableFields.length === checkedFields.length;
    const indeterminate =
      checkedFields.length > 0 && checkedFields.length < choosableFields.length;
    const sortableFields = useMemo(
      () => dragFields.filter((field) => checkedFields.includes(field.key)),
      [checkedFields, dragFields]
    );
    const activeField = activeFieldKey
      ? sortableFields.find((field) => field.key === activeFieldKey)
      : undefined;

    const resolveInitialPinned = (selectedKeys: string[]) => {
      const source =
        fixedFieldKeys != null ? fixedFieldKeys : defaultFixedFieldKeys;
      return source.filter((key) => selectedKeys.includes(key));
    };

    useImperativeHandle(ref, () => ({
      showModal: () => {
        setTitle(t('cutomTable.fieldSetting'));
        setCheckedFields(displayFieldKeys);
        const nextPinned = enableFixedFields
          ? resolveInitialPinned(displayFieldKeys)
          : [];
        const orderedFields = orderWithPinnedFirst(
          displayFieldKeys
            .map((key) => choosableFields.find((field) => field.key === key))
            .filter((field): field is ColumnItem => Boolean(field)),
          nextPinned
        );
        setPinnedFields(nextPinned);
        setDragFields(orderedFields);
        setSearchText('');
        setActiveFieldKey(null);
        setVisible(true);
      },
    }));

    const onCheckAllChange: CheckboxProps['onChange'] = (e) => {
      const nextKeys = e.target.checked
        ? choosableFields.map((item) => item.key)
        : [];
      setCheckedFields(nextKeys);
      const nextPinned = pinnedFields.filter((key) => nextKeys.includes(key));
      setPinnedFields(nextPinned);
      setDragFields(
        e.target.checked
          ? orderWithPinnedFirst(choosableFields, nextPinned)
          : []
      );
    };

    const handleCheckboxChange = (checkedValues: string[]) => {
      setCheckedFields(checkedValues);
      const checkedSet = new Set(checkedValues);
      const retainedFields = dragFields.filter((field) =>
        checkedSet.has(field.key)
      );
      const retainedKeys = new Set(retainedFields.map((field) => field.key));
      const fields = [
        ...retainedFields,
        ...choosableFields.filter(
          (field) => checkedSet.has(field.key) && !retainedKeys.has(field.key)
        ),
      ];
      const nextPinned = pinnedFields.filter((key) => checkedSet.has(key));
      setPinnedFields(nextPinned);
      setDragFields(orderWithPinnedFirst(fields, nextPinned));
    };

    const clearCheckedItem = (key: string) => {
      const fields = cloneDeep(dragFields);
      const targetIndex = fields.findIndex(
        (item: ColumnItem) => item.key === key
      );
      if (targetIndex !== -1) {
        fields.splice(targetIndex, 1);
        setDragFields(fields);
        setCheckedFields(fields.map((item: ColumnItem) => item.key));
        setPinnedFields((prev) => prev.filter((item) => item !== key));
      }
    };

    const handleTogglePin = (key: string) => {
      setPinnedFields((prev) => {
        const next = prev.includes(key)
          ? prev.filter((item) => item !== key)
          : [...prev, key];
        setDragFields((fields) => orderWithPinnedFirst(fields, next));
        return next;
      });
    };

    const handleClear = () => {
      setCheckedFields([]);
      setDragFields([]);
      setPinnedFields([]);
    };

    const handleSubmit = async () => {
      setSubmitting(true);
      try {
        const fieldKeys = dragFields.map((item) => item.key);
        const nextPinned = enableFixedFields
          ? fieldKeys.filter((key) => pinnedFields.includes(key))
          : undefined;
        await onConfirm(fieldKeys, nextPinned);
        handleCancel();
      } catch {
        // 请求层负责展示错误；保留弹窗和用户尚未保存的排序。
      } finally {
        setSubmitting(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
    };

    const handleDragStart = ({ active }: DragStartEvent) => {
      setActiveFieldKey(String(active.id));
    };

    const handleDragEnd = ({ active, over }: DragEndEvent) => {
      setActiveFieldKey(null);
      if (!over || active.id === over.id) return;

      setDragFields((fields) => {
        const oldIndex = fields.findIndex((field) => field.key === active.id);
        const newIndex = fields.findIndex((field) => field.key === over.id);
        if (oldIndex === -1 || newIndex === -1) return fields;
        const moved = arrayMove(fields, oldIndex, newIndex);
        return enableFixedFields
          ? orderWithPinnedFirst(moved, pinnedFields)
          : moved;
      });
    };

    const renderCheckBox = (fields: ColumnItem[]) => {
      const keyword = searchText.trim().toLocaleLowerCase();
      return fields
        .filter(
          (field) =>
            !keyword ||
            String(field.title).toLocaleLowerCase().includes(keyword)
        )
        .map((field) => (
          <Checkbox
            className="w-[166px] mb-[10px]"
            key={field.key}
            value={field.key}
          >
            <span
              title={field.title}
              className={fieldSettingModalStyle.fieldLabel}
            >
              {field.title}
            </span>
          </Checkbox>
        ));
    };

    return (
      <OperateModal
        visible={visible}
        title={title}
        width={width}
        onCancel={handleCancel}
        footer={
          <div>
            <Button
              disabled={!checkedFields.length}
              loading={submitting}
              className="mr-[10px]"
              type="primary"
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <div className={`${fieldSettingModalStyle.settingFields} flex`}>
          <div className={`${fieldSettingModalStyle.leftSide} w-2/3 p-4`}>
            {searchable && (
              <Input
                allowClear
                className="mb-[12px]"
                value={searchText}
                placeholder={t('common.searchPlaceHolder')}
                onChange={(event) => setSearchText(event.target.value)}
              />
            )}
            <div>
              <Checkbox
                className="mb-[10px]"
                indeterminate={indeterminate}
                onChange={onCheckAllChange}
                checked={checkAll}
              >
                {t('common.selectAll')}
              </Checkbox>
            </div>
            <Checkbox.Group
              value={checkedFields}
              onChange={handleCheckboxChange}
            >
              {groupFields?.length ? (
                groupFields.map((item) => (
                  <div key={item.key}>
                    <div className="font-bold mb-[10px]">{item.title}</div>
                    <div className="flex items-center flex-wrap">
                      {renderCheckBox(item.child)}
                    </div>
                  </div>
                ))
              ) : (
                <div className="flex items-center flex-wrap">
                  {renderCheckBox(choosableFields)}
                </div>
              )}
            </Checkbox.Group>
          </div>
          {/* Right drag list */}
          <div className={`${fieldSettingModalStyle.rightSide} w-1/3 p-4`}>
            <div className="flex justify-between items-center">
              <span>
                {t('common.selected')}(
                <span className="text-[var(--color-text-3)]">
                  {`${checkedFields.length} ${t('common.items')}`}
                </span>
                )
              </span>
              <Button type="link" onClick={handleClear}>
                {t('common.clear')}
              </Button>
            </div>
            {enableFixedFields && (
              <div className={fieldSettingModalStyle.pinHint}>
                {t('cutomTable.pinHint')}
              </div>
            )}
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragCancel={() => setActiveFieldKey(null)}
              onDragEnd={handleDragEnd}
            >
              <SortableContext
                items={sortableFields.map((field) => field.key)}
                strategy={verticalListSortingStrategy}
              >
                <div className={fieldSettingModalStyle.fieldList}>
                  {sortableFields.map((field) => (
                    <SortableFieldItem
                      key={field.key}
                      field={field}
                      pinned={pinnedFields.includes(field.key)}
                      enableFixedFields={enableFixedFields}
                      onRemove={clearCheckedItem}
                      onTogglePin={handleTogglePin}
                    />
                  ))}
                </div>
              </SortableContext>
              <DragOverlay>
                {activeField ? (
                  <FieldDragOverlay
                    field={activeField}
                    pinned={pinnedFields.includes(activeField.key)}
                    enableFixedFields={enableFixedFields}
                  />
                ) : null}
              </DragOverlay>
            </DndContext>
          </div>
        </div>
      </OperateModal>
    );
  }
);
FieldSettingModal.displayName = 'fieldSettingModal';
export default FieldSettingModal;
