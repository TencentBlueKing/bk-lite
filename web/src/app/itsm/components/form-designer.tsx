'use client';

import { DndContext, DragOverlay, PointerSensor, pointerWithin, useDraggable, useDroppable, useSensor, useSensors, type CollisionDetection, type DragEndEvent, type DragMoveEvent, type DragStartEvent } from '@dnd-kit/core';
import { SortableContext, rectSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button, Checkbox, DatePicker, Empty, Input, InputNumber, Radio, Select, Switch } from 'antd';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ALL_FIELDS, BASIC_FIELDS, CASCADE_TYPES, CHOICE_TYPES, FULL_ROW_TYPES, SCENE_FIELDS, SENIOR_FIELDS, fieldLabelId, type CatalogField } from '../constants/field-catalog';
import type { FormFieldSchema } from '../types';
import { ConditionBuilder } from './condition-builder';
import { CanvasTools } from './canvas-tools';
import { FIELD_GROUP_COLOR, FieldGlyph } from './field-glyph';
import { useTranslation } from '@/utils/i18n';

const WIDTHS = [
  { span: 3, label: '1/4' },
  { span: 4, label: '1/3' },
  { span: 6, label: '1/2' },
  { span: 8, label: '2/3' },
  { span: 9, label: '3/4' },
  { span: 12, label: '1' },
];

const columnClass: Record<number, string> = {
  3: 'col-span-3',
  4: 'col-span-4',
  6: 'col-span-6',
  8: 'col-span-8',
  9: 'col-span-9',
  12: 'col-span-12',
};

const fieldSpan = (field: FormFieldSchema) => {
  if (FULL_ROW_TYPES.has(field.type) || field.span === 24) {
    return 12;
  }
  return WIDTHS.some((item) => item.span === field.span) ? field.span || 6 : 6;
};

const visualRows = (list: FormFieldSchema[]) => {
  const rows: number[][] = [];
  let current: number[] = [];
  let used = 0;
  list.forEach((field, index) => {
    const span = fieldSpan(field);
    if (current.length && (field.rowBreak || used + span > 12)) {
      rows.push(current);
      current = [];
      used = 0;
    }
    current.push(index);
    used += span;
  });
  if (current.length) {
    rows.push(current);
  }
  return rows;
};

const equalSpan = (count: number) => (count <= 2 ? 6 : count === 3 ? 4 : 3);

const balanceKeys = (list: FormFieldSchema[], keys: string[]) => {
  const adjustable = keys.filter((key) => !FULL_ROW_TYPES.has(list.find((field) => field.key === key)?.type || ''));
  if (!adjustable.length || adjustable.length > 4) {
    return list;
  }
  const span = equalSpan(adjustable.length);
  const set = new Set(adjustable);
  return list.map((field) => (set.has(field.key) ? { ...field, span } : field));
};

const rowOf = (list: FormFieldSchema[], index: number) => visualRows(list).find((row) => row.includes(index)) || [index];

interface InsertGuide {
  anchor: string;
  edge: 'left' | 'right' | 'top' | 'bottom';
  scope: string;
  keys: string[];
}

const dropPoint = (event: DragEndEvent | DragMoveEvent) => {
  const start = event.activatorEvent;
  if (!start || !('clientX' in start) || !('clientY' in start)) {
    return null;
  }
  const x = start.clientX;
  const y = start.clientY;
  if (typeof x !== 'number' || typeof y !== 'number') {
    return null;
  }
  return { x: x + event.delta.x, y: y + event.delta.y };
};

const cardRects = (list: FormFieldSchema[]) => (
  [...document.querySelectorAll<HTMLElement>('[data-field-key]')]
    .map((element) => ({ key: element.dataset.fieldKey || '', rect: element.getBoundingClientRect() }))
    .filter((card) => list.some((item) => item.key === card.key))
);

const resolveGuide = (list: FormFieldSchema[], point: { x: number; y: number } | null, scope: string, skipKey = ''): InsertGuide | null => {
  if (!point || !list.length) {
    return null;
  }
  const cards = cardRects(list).filter((card) => card.key !== skipKey);
  const rows = visualRows(list).map((indexes) => {
    const visible = indexes.filter((index) => list[index].key !== skipKey);
    const rects = visible.map((index) => cards.find((card) => card.key === list[index].key)?.rect).filter((rect): rect is DOMRect => Boolean(rect));
    return {
      indexes: visible,
      top: rects.length ? Math.min(...rects.map((rect) => rect.top)) : 0,
      bottom: rects.length ? Math.max(...rects.map((rect) => rect.bottom)) : 0,
    };
  }).filter((row) => row.indexes.length && row.bottom > 0);
  const guideForRow = (indexes: number[], edge: 'top' | 'bottom'): InsertGuide => ({
    anchor: list[indexes[edge === 'top' ? 0 : indexes.length - 1]].key,
    edge,
    scope,
    keys: indexes.map((index) => list[index].key),
  });
  for (let index = 0; index < rows.length - 1; index += 1) {
    const upper = rows[index];
    const lower = rows[index + 1];
    const mid = (upper.bottom + lower.top) / 2;
    if (point.y >= upper.bottom - 18 && point.y <= lower.top + 18) {
      return point.y < mid ? guideForRow(upper.indexes, 'bottom') : guideForRow(lower.indexes, 'top');
    }
  }
  const band = rows.find((row) => point.y >= row.top && point.y <= row.bottom);
  if (!band) {
    if (rows[0] && point.y < rows[0].top) {
      return guideForRow(rows[0].indexes, 'top');
    }
    const last = rows[rows.length - 1];
    return last ? guideForRow(last.indexes, 'bottom') : null;
  }
  if (point.y <= band.top + 8) {
    return guideForRow(band.indexes, 'top');
  }
  if (point.y >= band.bottom - 8) {
    return guideForRow(band.indexes, 'bottom');
  }
  const items = band.indexes
    .map((index) => ({ index, rect: cards.find((card) => card.key === list[index].key)?.rect }))
    .filter((item): item is { index: number; rect: DOMRect } => Boolean(item.rect))
    .sort((left, right) => left.rect.left - right.rect.left);
  if (!items.length) {
    return guideForRow(band.indexes, 'bottom');
  }
  const blocked = items.some((item) => FULL_ROW_TYPES.has(list[item.index].type)) || band.indexes.length >= 4;
  if (blocked) {
    return guideForRow(band.indexes, point.y < band.top + (band.bottom - band.top) / 2 ? 'top' : 'bottom');
  }
  for (let index = 0; index < items.length - 1; index += 1) {
    const leftCard = items[index];
    const rightCard = items[index + 1];
    const seamStart = leftCard.rect.left + leftCard.rect.width * 0.35;
    const seamEnd = rightCard.rect.left + rightCard.rect.width * 0.65;
    if (point.x >= seamStart && point.x <= seamEnd) {
      return { anchor: list[leftCard.index].key, edge: 'right', scope, keys: [list[leftCard.index].key] };
    }
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (point.x <= first.rect.left + first.rect.width * 0.65) {
    return { anchor: list[first.index].key, edge: 'left', scope, keys: [list[first.index].key] };
  }
  return { anchor: list[last.index].key, edge: 'right', scope, keys: [list[last.index].key] };
};

const applyGuide = (list: FormFieldSchema[], field: FormFieldSchema, guide: InsertGuide | null) => {
  if (!guide) {
    return [...list, field];
  }
  const index = list.findIndex((item) => item.key === guide.anchor);
  if (index < 0) {
    return [...list, field];
  }
  if (guide.edge === 'left') {
    return insertIntoRow(list, index, field);
  }
  if (guide.edge === 'right') {
    const row = rowOf(list, index);
    if (row.length >= 4 || row.some((item) => FULL_ROW_TYPES.has(list[item].type)) || FULL_ROW_TYPES.has(field.type)) {
      const next = [...list];
      next.splice(row[row.length - 1] + 1, 0, field);
      return next;
    }
    const next = [...list];
    next.splice(index + 1, 0, { ...field, rowBreak: false });
    const keys = row.map((item) => list[item].key);
    keys.splice(keys.indexOf(guide.anchor) + 1, 0, field.key);
    return balanceKeys(next, keys);
  }
  const row = rowOf(list, index);
  const at = guide.edge === 'top' ? row[0] : row[row.length - 1] + 1;
  const next = [...list];
  const span = FULL_ROW_TYPES.has(field.type) ? 12 : field.span || 6;
  next.splice(at, 0, { ...field, span, rowBreak: true });
  if (next[at + 1]) {
    next[at + 1] = { ...next[at + 1], rowBreak: true };
  }
  return next;
};

const insertIntoRow = (list: FormFieldSchema[], index: number, field: FormFieldSchema) => {
  const row = rowOf(list, index);
  const rowLocked = FULL_ROW_TYPES.has(field.type) || row.some((item) => FULL_ROW_TYPES.has(list[item].type));
  if (rowLocked) {
    const next = [...list];
    const at = row[row.length - 1] + 1;
    next.splice(at, 0, { ...field, span: FULL_ROW_TYPES.has(field.type) ? 12 : field.span });
    return next;
  }
  if (row.length >= 4) {
    const next = [...list];
    next.splice(row[row.length - 1] + 1, 0, field);
    return next;
  }
  const next = [...list];
  next.splice(index, 0, { ...field, rowBreak: false });
  const keys = row.map((item) => list[item].key);
  keys.splice(row.indexOf(index), 0, field.key);
  return balanceKeys(next, keys);
};

interface FormDesignerProps {
  fields: FormFieldSchema[];
  onChange: (fields: FormFieldSchema[]) => void;
}

function PaletteControl({
  item,
  onAdd,
}: {
  item: CatalogField;
  onAdd: (item: CatalogField) => void;
}) {
  const dragId = item.key ? `scene:${item.key}` : `control:${item.type}`;
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: dragId,
    data: { catalogKey: item.key || item.type },
  });
  const origin = useRef<{ x: number; y: number } | null>(null);
  return (
    <div
      ref={setNodeRef}
      role="button"
      tabIndex={0}
      className={`group flex cursor-grab items-center gap-2 rounded-md bg-[var(--color-fill-1)] px-2 py-1.5 text-left transition-all hover:bg-[var(--color-fill-2)] active:cursor-grabbing ${
        isDragging ? 'opacity-40' : ''
      }`}
      {...listeners}
      {...attributes}
      onPointerDown={(event) => {
        origin.current = { x: event.clientX, y: event.clientY };
        listeners?.onPointerDown?.(event);
      }}
      onClick={(event) => {
        const start = origin.current;
        if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 6) {
          return;
        }
        onAdd(item);
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onAdd(item);
        }
      }}
    >
      <span className="shrink-0" style={{ color: FIELD_GROUP_COLOR[item.group] }}>
        <FieldGlyph type={item.type} />
      </span>
      <span className="truncate text-xs text-[var(--color-text-1)]">
        {t(fieldLabelId(item))}
      </span>
    </div>
  );
}

function CanvasPane({ children }: { children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'form-canvas' });
  return (
    <div
      id="itsm-form-canvas"
      ref={setNodeRef}
      className={`mx-auto flex h-full min-h-0 w-full flex-1 flex-col gap-3 overflow-y-auto overscroll-contain rounded-lg border bg-[var(--color-bg)] p-4 shadow-[0_1px_3px_rgba(0,0,0,0.03)] ${
        isOver ? 'border-[var(--color-primary)]' : 'border-[var(--color-border)]'
      }`}
    >
      {children}
    </div>
  );
}

function columnNames(field: FormFieldSchema) {
  const names = String(field.props?.columns || '')
    .split('\n')
    .map((line) => line.split(':')[0].trim())
    .filter(Boolean);
  return names.length ? names : ['列1', '列2'];
}

function TableSketch({ field }: { field: FormFieldSchema }) {
  const heads = columnNames(field);
  return (
    <div className="pointer-events-none overflow-hidden rounded border border-[var(--color-border)] text-xs">
      <div className="grid bg-[var(--color-fill-1)]" style={{ gridTemplateColumns: `repeat(${heads.length}, minmax(0,1fr))` }}>
        {heads.map((name) => (
          <div key={name} className="truncate px-2 py-1 text-[var(--color-text-3)]">{name}</div>
        ))}
      </div>
      <div className="px-2 py-2 text-[var(--color-text-3)]">{field.type === 'task' ? '添加任务' : '暂无数据'}</div>
    </div>
  );
}

function FieldPreview({ field }: { field: FormFieldSchema }) {
  const options = field.source?.options || [];
  const layout = field.optionLayout === 'vertical' ? 'flex flex-col gap-1' : '';
  const placeholder = field.placeholder || '请选择';
  if (field.type === 'radio') {
    return <Radio.Group disabled className={`pointer-events-none ${layout}`} options={options} />;
  }
  if (field.type === 'checkbox') {
    return <Checkbox.Group disabled className={`pointer-events-none ${layout}`} options={options} />;
  }
  if (field.type === 'select' || field.type === 'multiselect' || field.type === 'cascade' || field.type === 'multiCascade' || field.type === 'cmdb' || field.type === 'multiCmdb' || field.type === 'singleAssociateConfig' || field.type === 'associateConfig') {
    const multiple = field.type === 'multiselect' || field.type === 'multiCascade' || field.type === 'multiCmdb' || field.type === 'associateConfig';
    return <Select disabled className="pointer-events-none w-full" placeholder={placeholder} mode={multiple ? 'multiple' : undefined} options={options} />;
  }
  if (field.type === 'textarea' || field.type === 'richtext') {
    return <Input.TextArea disabled className="pointer-events-none" rows={field.type === 'richtext' ? 4 : field.rows || 2} placeholder={field.placeholder || '请输入'} />;
  }
  if (field.type === 'number' || field.type === 'calculate') {
    return <InputNumber disabled className="pointer-events-none w-full" placeholder={field.placeholder || String(field.props?.expr || '请输入')} />;
  }
  if (field.type === 'date') {
    return <DatePicker disabled className="pointer-events-none w-full" />;
  }
  if (field.type === 'datetime') {
    return <DatePicker disabled showTime className="pointer-events-none w-full" />;
  }
  if (field.type === 'time') {
    return <DatePicker disabled picker="time" className="pointer-events-none w-full" />;
  }
  if (field.type === 'dateRange') {
    return <DatePicker.RangePicker disabled className="pointer-events-none w-full" />;
  }
  if (field.type === 'organization' || field.type === 'userGroup' || field.type === 'multiUserGroup') {
    return <Select disabled className="pointer-events-none w-full" placeholder={field.placeholder || '选择组织'} mode={field.type === 'multiUserGroup' ? 'multiple' : undefined} />;
  }
  if (field.type === 'user' || field.type === 'multiUser') {
    return <Select disabled className="pointer-events-none w-full" placeholder={field.placeholder || '搜索用户'} mode={field.type === 'multiUser' ? 'multiple' : undefined} />;
  }
  if (field.type === 'attachment') {
    return <Button disabled className="pointer-events-none">上传附件</Button>;
  }
  if (field.type === 'link') {
    return <span className="text-sm text-[var(--color-primary)]">{String(field.props?.href || field.label || '链接')}</span>;
  }
  if (field.type === 'table' || field.type === 'nestedTable' || field.type === 'task' || field.type === 'cab') {
    return <TableSketch field={field} />;
  }
  if (field.type === 'tab') {
    return <div className="rounded border border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-text-3)]">{field.label}</div>;
  }
  if (field.type === 'subProcessForm') {
    return <div className="rounded border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-3)]">子流程表单</div>;
  }
  if (field.type === 'signature') {
    return <div className="flex h-16 items-center justify-center rounded border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-3)]">点击签名</div>;
  }
  if (field.type === 'section') {
    return null;
  }
  return <Input disabled className="pointer-events-none" placeholder={field.placeholder || '请输入'} />;
}

function SortableCard({ field, selected, guide, onSelect, onCopy, onRemove, children }: { field: FormFieldSchema; selected: boolean; guide?: InsertGuide | null; onSelect: () => void; onCopy: () => void; onRemove: () => void; children?: ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: field.key });
  const edge = guide?.keys.includes(field.key) ? guide.edge : null;
  const bar = 'pointer-events-none absolute z-10 bg-[var(--color-primary)]';
  return (
    <div
      ref={setNodeRef}
      data-field-key={field.key}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={`group relative flex cursor-grab flex-col gap-1.5 rounded-md border bg-[var(--color-bg)] px-3 py-2 transition-all active:cursor-grabbing ${columnClass[fieldSpan(field)]} ${field.rowBreak ? 'col-start-1' : ''} ${
        selected ? 'border-[var(--color-primary)]' : 'border-transparent hover:border-[var(--color-border)]'
      }`}
      {...attributes}
      {...listeners}
      onClick={(event) => {
        event.stopPropagation();
        onSelect();
      }}
    >
      {selected ? (
        <div className="absolute -top-3 right-1 z-20">
          <CanvasTools onCopy={onCopy} onDelete={onRemove} />
        </div>
      ) : null}
      <div className="flex items-center gap-1">
        <span className="text-xs font-medium text-[var(--color-text-1)]">
          {field.required ? <span className="mr-0.5 text-[var(--color-fail)]">*</span> : null}
          {field.label}
        </span>
      </div>
      {field.type === 'section' ? children : <FieldPreview field={field} />}
      {edge === 'left' ? <span className={`${bar} bottom-0 left-0 top-0 w-1`} /> : null}
      {edge === 'right' ? <span className={`${bar} bottom-0 right-0 top-0 w-1`} /> : null}
      {edge === 'top' ? <span className={`${bar} left-0 right-0 top-0 h-1`} /> : null}
      {edge === 'bottom' ? <span className={`${bar} bottom-0 left-0 right-0 h-1`} /> : null}
    </div>
  );
}

function GroupDrop({
  field,
  selectedKey,
  guide,
  onSelect,
  onCopy,
  onRemove,
}: {
  field: FormFieldSchema;
  selectedKey: string;
  guide?: InsertGuide | null;
  onSelect: (key: string) => void;
  onCopy: (key: string) => void;
  onRemove: (key: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `group:${field.key}` });
  const children = field.children || [];
  return (
    <div
      ref={setNodeRef}
      data-group-key={field.key}
      className={`min-h-16 rounded-md border border-dashed p-2 ${isOver ? 'border-[var(--color-primary)] bg-[var(--color-primary-bg)]' : 'border-[var(--color-border)] bg-[var(--color-fill-1)]'}`}
    >
      <SortableContext items={children.map((item) => item.key)} strategy={rectSortingStrategy}>
        <div className="grid grid-cols-12 gap-2">
          {children.map((item) => (
            <SortableCard
              key={item.key}
              field={item}
              guide={guide}
              selected={item.key === selectedKey}
              onSelect={() => onSelect(item.key)}
              onCopy={() => onCopy(item.key)}
              onRemove={() => onRemove(item.key)}
            />
          ))}
        </div>
      </SortableContext>
      {children.length ? null : <div className="py-3 text-center text-xs text-[var(--color-text-3)]">拖到分组里</div>}
    </div>
  );
}

export function FormDesigner({ fields, onChange }: FormDesignerProps) {
  const { t } = useTranslation();
  const [selectedKey, setSelectedKey] = useState(fields[0]?.key || '');
  const [paletteTab, setPaletteTab] = useState<'type' | 'scene'>('type');
  const [draggingKey, setDraggingKey] = useState('');
  const [guide, setGuide] = useState<InsertGuide | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const selected = fields.flatMap((field) => [field, ...(field.children || [])]).find((field) => field.key === selectedKey) || fields[0];
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  const removeField = (key: string) => {
    const visit = (list: FormFieldSchema[]): FormFieldSchema[] => list
      .filter((field) => field.key !== key)
      .map((field) => ({ ...field, children: field.children ? visit(field.children) : field.children }));
    const next = visit(fields);
    onChange(next);
    if (selectedKey === key) {
      const flat = next.flatMap((field) => [field, ...(field.children || [])]);
      setSelectedKey(flat[0]?.key || '');
    }
  };

  const copyField = (key: string) => {
    let copiedKey = '';
    const duplicate = (field: FormFieldSchema): FormFieldSchema => ({
      ...field,
      key: `${field.key}_${Math.random().toString(36).slice(2, 6)}`,
      children: field.children?.map(duplicate),
    });
    const visit = (list: FormFieldSchema[]): FormFieldSchema[] => list.flatMap((field) => {
      if (field.key === key) {
        const copied = duplicate(field);
        copiedKey = copied.key;
        return [field, copied];
      }
      return [{ ...field, children: field.children ? visit(field.children) : field.children }];
    });
    onChange(visit(fields));
    if (copiedKey) {
      setSelectedKey(copiedKey);
    }
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.key !== 'Backspace' && event.key !== 'Delete') || !selectedKey) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }
      event.preventDefault();
      removeField(selectedKey);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fields, selectedKey]);

  const patch = (key: string, next: Partial<FormFieldSchema>) => {
    const visit = (list: FormFieldSchema[]): FormFieldSchema[] => list.map((field) => (
      field.key === key
        ? { ...field, ...next }
        : { ...field, children: field.children ? visit(field.children) : field.children }
    ));
    onChange(visit(fields));
  };

  const usedKeys = new Set(fields.flatMap((field) => [field.key, ...(field.children || []).map((child) => child.key)]));

  const createField = (item: CatalogField): FormFieldSchema => {
    const baseKey = item.key || `${item.type}_${usedKeys.size + 1}`;
    const key = usedKeys.has(baseKey) ? `${baseKey}_${usedKeys.size + 1}` : baseKey;
    const choice = CHOICE_TYPES.has(item.type);
    return {
      key,
      type: item.type,
      label: t(fieldLabelId(item)),
      span: FULL_ROW_TYPES.has(item.type) ? 12 : 6,
      placeholder: item.placeholder,
      state: 'default',
      hideValueClearMode: 'keep',
      hideLogic: 'visible',
      optionLayout: item.type === 'radio' || item.type === 'checkbox' ? 'horizontal' : undefined,
      rows: item.type === 'textarea' ? 3 : undefined,
      source: choice ? { type: 'static', options: [{ label: '选项1', value: '1' }, { label: '选项2', value: '2' }] } : undefined,
    };
  };

  const add = (item: CatalogField) => {
    const field = createField(item);
    onChange([...fields, field]);
    setSelectedKey(field.key);
  };

  const catalogOf = (token: string) => ALL_FIELDS.find((item) => (item.key || item.type) === token);

  const onDragStart = (event: DragStartEvent) => {
    const token = String(event.active.data.current?.catalogKey || '');
    if (token) {
      setDraggingKey(token);
    }
  };

  const refreshGuide = (event: DragMoveEvent) => {
    const point = dropPoint(event);
    const scroller = document.getElementById('itsm-form-canvas');
    if (scroller && point) {
      const rect = scroller.getBoundingClientRect();
      if (point.y > rect.bottom - 72) {
        scroller.scrollTop += 28;
      } else if (point.y < rect.top + 72) {
        scroller.scrollTop -= 28;
      }
    }
    const activeId = String(event.active.id);
    const group = [...document.querySelectorAll<HTMLElement>('[data-group-key]')].find((element) => {
      if (!point) {
        return false;
      }
      const rect = element.getBoundingClientRect();
      return point.x >= rect.left && point.x <= rect.right && point.y >= rect.top && point.y <= rect.bottom;
    });
    if (group) {
      const parent = fields.find((field) => field.key === group.dataset.groupKey);
      setGuide(parent ? resolveGuide(parent.children || [], point, parent.key, activeId) : null);
      return;
    }
    setGuide(resolveGuide(fields, point, '', activeId.startsWith('control:') || activeId.startsWith('scene:') ? '' : activeId));
  };

  const onDragEnd = (event: DragEndEvent) => {
    const currentGuide = guide;
    setDraggingKey('');
    setGuide(null);
    const { active, over } = event;
    if (!over && !currentGuide) {
      return;
    }
    const token = String(active.data.current?.catalogKey || '');
    const catalog = catalogOf(token);
    if (catalog) {
      const field = createField(catalog);
      if (currentGuide?.scope) {
        if (field.type === 'section') {
          return;
        }
        onChange(fields.map((item) => (
          item.key === currentGuide.scope ? { ...item, children: applyGuide(item.children || [], field, currentGuide) } : item
        )));
        setSelectedKey(field.key);
        return;
      }
      onChange(applyGuide(fields, field, currentGuide));
      setSelectedKey(field.key);
      return;
    }
    if (!currentGuide || String(active.id) === currentGuide.anchor) {
      return;
    }
    const activeId = String(active.id);
    const moving = fields.find((field) => field.key === activeId)
      || fields.flatMap((field) => field.children || []).find((field) => field.key === activeId);
    if (!moving || (currentGuide.scope && moving.type === 'section')) {
      return;
    }
    const rest = fields
      .filter((field) => field.key !== activeId)
      .map((field) => ({ ...field, children: field.children?.filter((child) => child.key !== activeId) }));
    if (currentGuide.scope) {
      onChange(rest.map((item) => (
        item.key === currentGuide.scope ? { ...item, children: applyGuide(item.children || [], moving, currentGuide) } : item
      )));
      return;
    }
    onChange(applyGuide(rest, moving, currentGuide));
  };

  const collision: CollisionDetection = (args) => {
    const inside = pointerWithin(args);
    const child = inside.find((item) => fields.some((field) => field.children?.some((entry) => entry.key === item.id)));
    if (child) {
      return [child];
    }
    const group = inside.find((item) => String(item.id).startsWith('group:'));
    if (group) {
      return [group];
    }
    const card = inside.find((item) => fields.some((field) => field.key === item.id));
    if (card) {
      return [card];
    }
    const canvas = inside.find((item) => item.id === 'form-canvas');
    return canvas ? [canvas] : [];
  };

  const dragging = catalogOf(draggingKey);
  const paletteGroups = paletteTab === 'type'
    ? [{ name: t('itsm.admin.basicFields'), tone: 'basic' as const, items: BASIC_FIELDS }, { name: t('itsm.admin.seniorFields'), tone: 'senior' as const, items: SENIOR_FIELDS }]
    : [{ name: t('itsm.admin.sceneFields'), tone: 'scene' as const, items: SCENE_FIELDS }];

  return (
    <DndContext sensors={sensors} collisionDetection={collision} onDragStart={onDragStart} onDragMove={refreshGuide} onDragEnd={onDragEnd} onDragCancel={() => { setDraggingKey(''); setGuide(null); }}>
    <div className="grid h-full min-h-0 items-stretch overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]" style={{ gridTemplateColumns: `${leftOpen ? 240 : 28}px minmax(0,1fr) ${rightOpen ? 300 : 28}px` }}>
      <div className={`relative flex h-full min-h-0 flex-col gap-3 overflow-hidden border-r border-[var(--color-border)] bg-[var(--color-bg)] ${leftOpen ? 'p-4' : 'p-1'}`}>
        <button type="button" aria-label={leftOpen ? '收起控件' : '展开控件'} className="absolute top-1/2 -right-3 z-20 flex h-12 w-6 -translate-y-1/2 items-center justify-center rounded-full bg-[var(--color-primary)] text-white shadow-md" onClick={() => setLeftOpen((open) => !open)}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d={leftOpen ? 'M9 2.5 L4.5 7 L9 11.5' : 'M5 2.5 L9.5 7 L5 11.5'} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {leftOpen ? <>
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-[var(--color-fill-1)] p-1">
          <button type="button" className={`rounded px-2 py-1 text-xs ${paletteTab === 'type' ? 'bg-[var(--color-bg)] font-medium text-[var(--color-text-1)]' : 'text-[var(--color-text-3)]'}`} onClick={() => setPaletteTab('type')}>字段类型</button>
          <button type="button" className={`rounded px-2 py-1 text-xs ${paletteTab === 'scene' ? 'bg-[var(--color-bg)] font-medium text-[var(--color-text-1)]' : 'text-[var(--color-text-3)]'}`} onClick={() => setPaletteTab('scene')}>{t('itsm.admin.sceneTab')}</button>
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {paletteGroups.map((group) => (
            <div key={group.name} className="flex flex-col gap-1.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-1)]">
                <span className="h-3 w-0.5 rounded-full" style={{ background: FIELD_GROUP_COLOR[group.tone] }} />
                {group.name}
              </div>
              {group.items.map((item) => (
                <PaletteControl key={item.key || item.type} item={item} onAdd={add} />
              ))}
            </div>
          ))}
        </div>
        </> : null}
      </div>

      <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--color-fill-1)] p-2">
        <CanvasPane>
          <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-3">
            <div className="text-sm font-medium text-[var(--color-text-1)]">表单画布</div>
          </div>
          {fields.length ? (
            <SortableContext items={fields.map((field) => field.key)} strategy={rectSortingStrategy}>
              <div className="grid min-h-full grid-cols-12 content-start gap-3 pb-48">
                {fields.map((field) => (
                  <SortableCard
                    key={field.key}
                    field={field}
                    guide={guide}
                    selected={field.key === selected?.key}
                    onSelect={() => setSelectedKey(field.key)}
                    onCopy={() => copyField(field.key)}
                    onRemove={() => removeField(field.key)}
                  >
                    {field.type === 'section' ? (
                      <GroupDrop field={field} guide={guide} selectedKey={selectedKey} onSelect={setSelectedKey} onCopy={copyField} onRemove={removeField} />
                    ) : null}
                  </SortableCard>
                ))}
              </div>
            </SortableContext>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-fill-1)] py-20">
              <Empty description="把左侧控件拖到这里" />
            </div>
          )}
        </CanvasPane>
      </div>

      <div className={`relative flex h-full min-h-0 flex-col gap-3 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-bg)] ${rightOpen ? 'p-4' : 'overflow-hidden p-1'}`}>
        <button type="button" aria-label={rightOpen ? '收起属性' : '展开属性'} className="absolute top-1/2 -left-3 z-20 flex h-12 w-6 -translate-y-1/2 items-center justify-center rounded-full bg-[var(--color-primary)] text-white shadow-md" onClick={() => setRightOpen((open) => !open)}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path d={rightOpen ? 'M5 2.5 L9.5 7 L5 11.5' : 'M9 2.5 L4.5 7 L9 11.5'} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {rightOpen ? <>
        <div className="border-b border-[var(--color-border)] pb-2.5">
          <div className="text-sm font-medium text-[var(--color-text-1)]">字段属性</div>
        </div>
        {selected ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--color-text-2)]">字段名称</span>
              <Input value={selected.label} placeholder="标签" onChange={(event) => patch(selected.key, { label: event.target.value })} />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--color-text-2)]">字段标识 (Key)</span>
              <Input value={selected.key} placeholder="key" onChange={(event) => patch(selected.key, { key: event.target.value })} />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--color-text-2)]">提示文字</span>
              <Input value={selected.placeholder || ''} placeholder="请输入" onChange={(event) => patch(selected.key, { placeholder: event.target.value })} />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--color-text-2)]">描述信息</span>
              <Input.TextArea rows={3} value={selected.hint || ''} placeholder="请输入" onChange={(event) => patch(selected.key, { hint: event.target.value })} />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--color-text-2)]">状态</span>
              <div className="grid grid-cols-4 overflow-hidden rounded-lg border border-[var(--color-border)] text-xs">
                {([
                  ['default', '默认'],
                  ['disabled', '禁用'],
                  ['readonly', '只读'],
                  ['hidden', '隐藏'],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={`px-1 py-1.5 ${(selected.state || 'default') === value ? 'bg-[var(--color-primary)] text-white' : 'bg-[var(--color-bg)] text-[var(--color-text-2)]'}`}
                    onClick={() => patch(selected.key, { state: value })}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {(selected.state || 'default') === 'hidden' ? (
              <>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-[var(--color-text-2)]">隐藏后清空字段值</span>
                  <Radio.Group
                    value={selected.hideValueClearMode || 'keep'}
                    options={[{ label: '立即清空', value: 'clear' }, { label: '保留已填', value: 'keep' }]}
                    onChange={(event) => patch(selected.key, { hideValueClearMode: event.target.value })}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-[var(--color-text-2)]">隐藏字段提交设置</span>
                  <Select
                    value={selected.hideLogic || 'visible'}
                    options={[{ value: 'visible', label: '可见时提交值' }, { value: 'always', label: '始终提交' }]}
                    onChange={(hideLogic) => patch(selected.key, { hideLogic })}
                  />
                </div>
              </>
            ) : null}
            <FieldTypeProps field={selected} patch={patch} />
            {CASCADE_TYPES.has(selected.type) ? (
              <div className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] p-3">
                <span className="text-xs font-medium text-[var(--color-text-2)]">设置</span>
                <label className="flex items-center gap-2 text-xs text-[var(--color-text-1)]">
                  <input type="checkbox" checked={Boolean(selected.cascadeAnyLevel)} onChange={(event) => patch(selected.key, { cascadeAnyLevel: event.target.checked })} />
                  允许选择任一层级
                </label>
                <label className="flex items-center gap-2 text-xs text-[var(--color-text-1)]">
                  <input type="checkbox" checked={selected.showCascadePath !== false} onChange={(event) => patch(selected.key, { showCascadePath: event.target.checked })} />
                  选择结果显示层级路径
                </label>
              </div>
            ) : null}
            <div className="flex flex-col gap-2 border-t border-[var(--color-border)] pt-3">
              <span className="text-xs font-semibold text-[var(--color-text-2)]">校验</span>
              <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] px-3 py-2">
                <span className="text-xs font-medium text-[var(--color-text-1)]">必填</span>
                <Switch checked={Boolean(selected.required)} onChange={(required) => patch(selected.key, { required })} />
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-[var(--color-text-2)]">宽度</span>
              <div className="flex overflow-hidden rounded-lg border border-[var(--color-border)] text-xs">
                {WIDTHS.map((item, index) => {
                  const locked = FULL_ROW_TYPES.has(selected.type) && item.span !== 12;
                  return (
                    <button
                      key={item.span}
                      type="button"
                      disabled={locked}
                      className={`flex-1 px-1 py-1.5 ${index ? 'border-l border-[var(--color-border)]' : ''} ${fieldSpan(selected) === item.span ? 'bg-[var(--color-bg)] font-semibold text-[var(--color-text-1)] shadow-xs' : 'bg-[var(--color-fill-1)] text-[var(--color-text-2)]'} ${locked ? 'cursor-not-allowed opacity-40' : ''}`}
                      onClick={() => patch(selected.key, { span: item.span })}
                    >
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="flex flex-col gap-2 border-t border-[var(--color-border)] pt-3">
              <span className="text-xs font-semibold text-[var(--color-text-2)]">显隐条件</span>
              <ConditionBuilder
                fields={fields.map((field) => field.key)}
                value={selected.visibleWhen || undefined}
                onChange={(visibleWhen) => patch(selected.key, { visibleWhen })}
              />
            </div>
          </div>
        ) : (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-fill-1)] py-16">
            <Empty description="请先选择对应组件以配置字段属性" />
          </div>
        )}
        </> : null}
      </div>
    </div>
    <DragOverlay>
      {dragging ? (
        <div className="flex cursor-grabbing items-center gap-2 rounded-md bg-[var(--color-fill-1)] px-2 py-1.5 shadow-xs">
          <span className="shrink-0" style={{ color: FIELD_GROUP_COLOR[dragging.group] }}>
            <FieldGlyph type={dragging.type} />
          </span>
          <span className="text-xs text-[var(--color-text-1)]">{dragging.label}</span>
        </div>
      ) : null}
    </DragOverlay>
    </DndContext>
  );
}

function OptionEditor({ field, patch }: { field: FormFieldSchema; patch: (key: string, next: Partial<FormFieldSchema>) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-[var(--color-text-2)]">选项</span>
      <Select
        value={field.source?.type || 'static'}
        options={[{ value: 'static', label: '自定义' }, { value: 'dictionary', label: '数据字典' }]}
        onChange={(type) => patch(field.key, { source: { type, options: field.source?.options?.length ? field.source.options : [{ label: '选项1', value: '1' }, { label: '选项2', value: '2' }] } })}
      />
      {(field.source?.type || 'static') === 'static' ? (
        <Input.TextArea
          rows={4}
          placeholder={'选项1:1\n选项2:2'}
          value={(field.source?.options || []).map((item) => `${item.label}:${item.value}`).join('\n')}
          onChange={(event) => patch(field.key, {
            source: {
              type: 'static',
              options: event.target.value.split('\n').filter(Boolean).map((line) => {
                const [label, optionValue] = line.split(':');
                return { label: label || '', value: optionValue || label || '' };
              }),
            },
          })}
        />
      ) : (
        <Input
          placeholder="字典编码"
          value={String(field.props?.dictionary || '')}
          onChange={(event) => patch(field.key, { source: { type: 'dictionary', options: [] }, props: { ...field.props, dictionary: event.target.value } })}
        />
      )}
    </div>
  );
}

function FieldTypeProps({ field, patch }: { field: FormFieldSchema; patch: (key: string, next: Partial<FormFieldSchema>) => void }) {
  const setProp = (key: string, value: unknown) => patch(field.key, { props: { ...field.props, [key]: value } });
  return (
    <>
      {CHOICE_TYPES.has(field.type) ? <OptionEditor field={field} patch={patch} /> : null}
      {field.type === 'radio' || field.type === 'checkbox' ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-2)]">排列</span>
          <Radio.Group
            value={field.optionLayout || 'horizontal'}
            options={[{ label: '横向', value: 'horizontal' }, { label: '纵向', value: 'vertical' }]}
            onChange={(event) => patch(field.key, { optionLayout: event.target.value })}
          />
        </div>
      ) : null}
      {field.type === 'number' ? (
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder="最小值" value={String(field.props?.min ?? '')} onChange={(event) => setProp('min', event.target.value)} />
          <Input placeholder="最大值" value={String(field.props?.max ?? '')} onChange={(event) => setProp('max', event.target.value)} />
          <Input className="col-span-2" placeholder="小数位数" value={String(field.props?.precision ?? '')} onChange={(event) => setProp('precision', event.target.value)} />
        </div>
      ) : null}
      {field.type === 'textarea' ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-2)]">可见行数</span>
          <Input value={String(field.rows || 3)} onChange={(event) => patch(field.key, { rows: Number(event.target.value) || 3 })} />
        </div>
      ) : null}
      {field.type === 'time' ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-2)]">时间步长（分钟）</span>
          <Input value={String(field.props?.step ?? 1)} onChange={(event) => setProp('step', event.target.value)} />
        </div>
      ) : null}
      {field.type === 'attachment' ? (
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder="个数上限" value={String(field.props?.count ?? '')} onChange={(event) => setProp('count', event.target.value)} />
          <Input placeholder="大小 MB" value={String(field.props?.size ?? '')} onChange={(event) => setProp('size', event.target.value)} />
        </div>
      ) : null}
      {field.type === 'section' ? (
        <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-3 py-2">
          <span className="text-xs text-[var(--color-text-1)]">默认折叠</span>
          <Switch checked={Boolean(field.props?.fold)} onChange={(fold) => setProp('fold', fold)} />
        </div>
      ) : null}
      {field.type === 'calculate' ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-2)]">计算公式</span>
          <Input placeholder="sum(明细.数量)" value={String(field.props?.expr || '')} onChange={(event) => setProp('expr', event.target.value)} />
        </div>
      ) : null}
      {field.type === 'link' ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-2)]">链接地址</span>
          <Input placeholder="https://" value={String(field.props?.href || '')} onChange={(event) => setProp('href', event.target.value)} />
        </div>
      ) : null}
      {field.type === 'table' || field.type === 'nestedTable' || field.type === 'task' ? (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-[var(--color-text-2)]">列（一行一个：名称:标识）</span>
          <Input.TextArea rows={3} value={String(field.props?.columns || '')} onChange={(event) => setProp('columns', event.target.value)} />
        </div>
      ) : null}
    </>
  );
}
