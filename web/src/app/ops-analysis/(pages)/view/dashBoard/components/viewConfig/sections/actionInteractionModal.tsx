import React, { useEffect, useMemo, useRef, useState } from 'react';
import useUnsavedConfirm from '@/hooks/useUnsavedConfirm';
import {
  AutoComplete,
  Button,
  Input,
  message,
  Modal,
  Select,
  Space,
} from 'antd';
import {
  MinusCircleOutlined,
  PlusCircleOutlined,
} from '@ant-design/icons';
import type {
  DashboardActionConfig,
  DashboardActionParamMapping,
} from '@/app/ops-analysis/types/dashBoard';
import type { DisplayColumnRow } from '../utils/columnProbing';

interface FieldOption {
  label: string;
  value: string;
}

interface ActionInteractionModalProps {
  open: boolean;
  column?: DisplayColumnRow | null;
  actions: DashboardActionConfig[];
  fieldOptions: FieldOption[];
  t: (key: string) => string;
  onCancel: () => void;
  onConfirm: (nextActions: DashboardActionConfig[]) => void;
}

interface LocalDashboardAction extends DashboardActionConfig {
  id: string;
}

const createActionId = () =>
  `action_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;

const getColumnActionKey = (column?: DisplayColumnRow | null) =>
  column?.key || column?.id || '';

const createDefaultAction = (columnKey: string): LocalDashboardAction => ({
  id: createActionId(),
  columnKey,
  text: '查看',
  url: '',
  openMode: 'sameTab',
  params: [],
});

const isBlankMapping = (mapping: DashboardActionParamMapping) => {
  const hasTarget = !!mapping.key?.trim();
  if (!hasTarget) return true;

  if (mapping.source === 'rowField') {
    return !mapping.sourceKey;
  }

  return mapping.value === null || mapping.value === undefined || mapping.value === '';
};

const sanitizeMappings = (mappings?: DashboardActionParamMapping[]) =>
  (mappings || []).filter((mapping) => !isBlankMapping(mapping));

// 生成动作配置快照（忽略随机 id），用于关闭时的脏检查
const snapshotActions = (list: LocalDashboardAction[]) =>
  JSON.stringify(list.map((action) => ({ ...action, id: undefined })));

export const ActionInteractionModal: React.FC<ActionInteractionModalProps> = ({
  open,
  column,
  actions,
  fieldOptions,
  t,
  onCancel,
  onConfirm,
}) => {
  const [localActions, setLocalActions] = useState<LocalDashboardAction[]>([]);
  const guardClose = useUnsavedConfirm();
  const initialSnapshotRef = useRef<string>('');
  const columnActionKey = getColumnActionKey(column);

  const columnActions = useMemo(() => {
    if (!columnActionKey) return [];
    return actions.filter((action) => action.columnKey === columnActionKey);
  }, [actions, columnActionKey]);

  const paramKeyOptions = useMemo(
    () =>
      fieldOptions.map((field) => ({
        value: field.value,
        label: field.label ? `${field.value}（${field.label}）` : field.value,
      })),
    [fieldOptions],
  );

  useEffect(() => {
    if (!open || !columnActionKey) {
      return;
    }

    const nextActions =
      columnActions.length > 0
        ? columnActions.map((action) => ({
          ...action,
          id: createActionId(),
        }))
        : [createDefaultAction(columnActionKey)];
    setLocalActions(nextActions);
    initialSnapshotRef.current = snapshotActions(nextActions);
  }, [open, columnActionKey, columnActions]);

  const handleCancel = () =>
    guardClose(snapshotActions(localActions) !== initialSnapshotRef.current, onCancel);

  const replaceLocalAction = (
    actionId: string,
    updater: (action: LocalDashboardAction) => LocalDashboardAction,
  ) => {
    setLocalActions((prev) =>
      prev.map((action) => (action.id === actionId ? updater(action) : action)),
    );
  };

  const handleMappingChange = (
    actionId: string,
    index: number,
    patch: Partial<DashboardActionParamMapping>,
  ) => {
    replaceLocalAction(actionId, (action) => {
      const mappings = [...(action.params || [])];
      mappings[index] = { ...mappings[index], ...patch };
      if (patch.source === 'rowField') {
        delete mappings[index].value;
      }
      if (patch.source === 'fixed') {
        delete mappings[index].sourceKey;
        mappings[index].value = mappings[index].value ?? '';
      }
      return { ...action, params: mappings };
    });
  };

  const handleAddMapping = (actionId: string, insertAfterIndex?: number) => {
    replaceLocalAction(actionId, (action) => ({
      ...action,
      params: (() => {
        const mappings = action.params || [];
        const nextMapping: DashboardActionParamMapping = {
          key: '',
          source: 'rowField',
        };

        if (typeof insertAfterIndex !== 'number') {
          return [...mappings, nextMapping];
        }

        return [
          ...mappings.slice(0, insertAfterIndex + 1),
          nextMapping,
          ...mappings.slice(insertAfterIndex + 1),
        ];
      })(),
    }));
  };

  const handleDeleteMapping = (actionId: string, index: number) => {
    replaceLocalAction(actionId, (action) => ({
      ...action,
      params: (action.params || []).filter((_, idx) => idx !== index),
    }));
  };

  const handleAddAction = () => {
    if (!columnActionKey) return;
    setLocalActions((prev) => [...prev, createDefaultAction(columnActionKey)]);
  };

  const handleConfirm = () => {
    if (!columnActionKey) {
      onCancel();
      return;
    }

    const nextColumnActions = localActions
      .filter((action) => action.text.trim())
      .map<DashboardActionConfig>((action) => {
        const nextAction: DashboardActionConfig = {
          columnKey: columnActionKey,
          text: action.text.trim(),
          openMode: action.openMode || 'sameTab',
        };
        const url = action.url?.trim();
        const params = sanitizeMappings(action.params);
        if (url) {
          nextAction.url = url;
        }
        if (params.length > 0) {
          nextAction.params = params;
        }
        return nextAction;
      });

    onConfirm([
      ...actions.filter((action) => action.columnKey !== columnActionKey),
      ...nextColumnActions,
    ]);
    message.success(t('common.done'));
  };

  const renderField = (label: string, control: React.ReactNode) => (
    <div className="min-w-0">
      <div className="mb-1.5 text-xs font-medium text-(--color-text-3)">
        {label}
      </div>
      {control}
    </div>
  );

  const renderMappings = (action: LocalDashboardAction) => {
    const mappings = action.params || [];

    return (
      <div className="space-y-2.5">
        <div className="flex items-center gap-1 text-xs font-medium text-(--color-text-2)">
          <span>{t('dashboard.paramMapping')}</span>
          {mappings.length === 0 && (
            <Button
              type="text"
              title={t('common.add')}
              icon={<PlusCircleOutlined />}
              onClick={() => handleAddMapping(action.id)}
            />
          )}
        </div>
        {mappings.length > 0 && (
          <div className="grid grid-cols-[1fr_110px_1.2fr_64px] gap-2.5 text-xs font-medium text-(--color-text-3)">
            <span>{t('dashboard.targetParam')}</span>
            <span>{t('dashboard.sourceType')}</span>
            <span>{t('dashboard.sourceValue')}</span>
            <span />
          </div>
        )}
        {mappings.length === 0 && (
          <div className="py-2 text-center">
            <span className="text-xs text-(--color-text-3)">
              {t('dashboard.noParamMappings')}
            </span>
          </div>
        )}
        {mappings.map((mapping, index) => (
          <div
            key={`${action.id}_${index}`}
            className="grid grid-cols-[1fr_110px_1.2fr_64px] items-center gap-2.5"
          >
            <AutoComplete
              value={mapping.key}
              placeholder={t('dashboard.selectOrInputUrlParam')}
              options={paramKeyOptions}
              filterOption={(inputValue, option) => {
                const query = inputValue.toLowerCase();
                return (
                  String(option?.value || '')
                    .toLowerCase()
                    .includes(query) ||
                  String(option?.label || '')
                    .toLowerCase()
                    .includes(query)
                );
              }}
              onChange={(value) =>
                handleMappingChange(action.id, index, {
                  key: value,
                })
              }
            />
            <Select
              value={mapping.source}
              options={[
                { label: t('dashboard.rowField'), value: 'rowField' },
                { label: t('dashboard.fixedValue'), value: 'fixed' },
              ]}
              onChange={(value) =>
                handleMappingChange(action.id, index, { source: value })
              }
            />
            {mapping.source === 'rowField' ? (
              <Select
                value={mapping.sourceKey}
                placeholder={t('common.selectTip')}
                options={fieldOptions}
                showSearch
                optionFilterProp="label"
                onChange={(value) =>
                  handleMappingChange(action.id, index, { sourceKey: value })
                }
              />
            ) : (
              <Input
                value={
                  mapping.value === null || mapping.value === undefined
                    ? ''
                    : String(mapping.value)
                }
                placeholder={t('common.inputMsg')}
                onChange={(event) =>
                  handleMappingChange(action.id, index, {
                    value: event.target.value,
                  })
                }
              />
            )}
            <Space size={0}>
              <Button
                type="text"
                title={t('common.add')}
                icon={<PlusCircleOutlined />}
                onClick={() => handleAddMapping(action.id, index)}
              />
              <Button
                type="text"
                title={t('common.delete')}
                icon={<MinusCircleOutlined />}
                onClick={() => handleDeleteMapping(action.id, index)}
              />
            </Space>
          </div>
        ))}
      </div>
    );
  };

  const renderActionEditor = (action: LocalDashboardAction, index: number) => (
    <div
      key={action.id}
      className="grid grid-cols-[34px_1fr] items-start gap-3.5 rounded-lg border border-(--color-border-1) p-[18px_16px_18px_14px] shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-[0_8px_18px_rgba(15,23,42,0.08)]"
    >
      <span className="mt-0.5 inline-flex h-[22px] w-[22px] items-center justify-center rounded-full bg-blue-50 text-xs font-semibold text-blue-600">
        {index + 1}
      </span>
      <div className="space-y-4">
        <div className="grid grid-cols-[0.9fr_1.5fr_auto] items-end gap-2">
          {renderField(
            t('dashboard.actionText'),
            <Input
              value={action.text}
              placeholder={t('dashboard.actionText')}
              onChange={(event) =>
                replaceLocalAction(action.id, (current) => ({
                  ...current,
                  text: event.target.value,
                }))
              }
            />,
          )}
          {renderField(
            t('dashboard.targetUrl'),
            <Input
              value={action.url}
              placeholder={t('dashboard.targetUrlPlaceholder')}
              onChange={(event) =>
                replaceLocalAction(action.id, (current) => ({
                  ...current,
                  url: event.target.value,
                }))
              }
            />,
          )}
          {renderField(
            t('dashboard.openMode'),
            <div className="flex items-center gap-1">
              <Select
                className="w-[120px]"
                value={action.openMode || 'sameTab'}
                options={[
                  { label: t('dashboard.sameTab'), value: 'sameTab' },
                  { label: t('dashboard.newTab'), value: 'newTab' },
                ]}
                onChange={(value) =>
                  replaceLocalAction(action.id, (current) => ({
                    ...current,
                    openMode: value,
                  }))
                }
              />
              <Button
                type="text"
                title={t('common.delete')}
                icon={<MinusCircleOutlined />}
                disabled={localActions.length <= 1}
                onClick={() =>
                  setLocalActions((prev) =>
                    prev.filter((item) => item.id !== action.id),
                  )
                }
              />
            </div>,
          )}
        </div>
        {renderMappings(action)}
      </div>
    </div>
  );

  return (
    <Modal
      title={t('dashboard.interactionConfig')}
      width={820}
      open={open}
      centered
      maskClosable={false}
      onCancel={handleCancel}
      onOk={handleConfirm}
      destroyOnClose
      styles={{
        body: {
          maxHeight: 'calc(100vh - 320px)',
          overflowY: 'auto',
          paddingRight: 8,
        },
      }}
    >
      <div>
        <div className="sticky top-0 z-10 mb-2 flex justify-end bg-(--color-bg-1) pb-3">
          <Button
            type="dashed"
            icon={<PlusCircleOutlined />}
            onClick={handleAddAction}
          >
            {t('dashboard.addActionItem')}
          </Button>
        </div>
        <div className="space-y-3">
          {localActions.map((action, index) =>
            renderActionEditor(action, index),
          )}
        </div>
      </div>
    </Modal>
  );
};
