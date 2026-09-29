'use client';

import React, {
  forwardRef,
  useImperativeHandle,
  useMemo,
  useState
} from 'react';
import {
  Button,
  Cascader,
  Checkbox,
  Form,
  Input,
  Select,
  message
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useCommon } from '@/app/monitor/context/common';
import OperateModal from '@/components/operate-modal';
import useIntegrationApi from '@/app/monitor/api/integration';
import { MetricItem } from '@/app/monitor/types';
import ScriptMetricGroupSelect from '../configure/scriptMetricGroupSelect';
import {
  CatalogMetricGroupOption,
  buildUnitCascaderOptions,
  resolvePersistCatalogUnitId
} from '../configure/scriptMetricPersist';
import { EnumItem } from '@/app/monitor/types/integration';
import { PlusOutlined, MinusOutlined } from '@ant-design/icons';
import { cloneDeep } from 'lodash';

const { Option } = Select;
const INIT_ENUM_ITEM: EnumItem = { name: null, id: null, color: '#000000' };

export interface MetricBatchEditModalRef {
  showModal: (config: {
    metrics: MetricItem[];
    groups: CatalogMetricGroupOption[];
  }) => void;
}

interface MetricBatchEditModalProps {
  monitorObject: number;
  pluginId: number;
  onSuccess: () => void;
  onGroupListChange?: (group?: CatalogMetricGroupOption) => void;
}

type BatchField = 'metric_group' | 'unit' | 'data_type' | 'description';

const MetricBatchEditModal = forwardRef<
  MetricBatchEditModalRef,
  MetricBatchEditModalProps
>(({ monitorObject, pluginId, onSuccess, onGroupListChange }, ref) => {
  const { t } = useTranslation();
  const { batchUpdateMonitorMetrics } = useIntegrationApi();
  const [form] = Form.useForm();
  const commonContext = useCommon();
  const unitOptions = useMemo(
    () => buildUnitCascaderOptions(commonContext?.groupedUnitList || []),
    [commonContext?.groupedUnitList]
  );
  const [visible, setVisible] = useState(false);
  const [confirmLoading, setConfirmLoading] = useState(false);
  const [metrics, setMetrics] = useState<MetricItem[]>([]);
  const [groups, setGroups] = useState<CatalogMetricGroupOption[]>([]);
  const [enabledFields, setEnabledFields] = useState<Record<BatchField, boolean>>(
    {
      metric_group: false,
      unit: false,
      data_type: false,
      description: false
    }
  );
  const [enumList, setEnumList] = useState<EnumItem[]>([{ ...INIT_ENUM_ITEM }]);
  const dataType = Form.useWatch('data_type', form);
  const hasEnumSelected = metrics.some(
    (item) => String(item.data_type || '') === 'Enum'
  );

  useImperativeHandle(ref, () => ({
    showModal: ({ metrics: nextMetrics, groups: nextGroups }) => {
      setMetrics(nextMetrics);
      setGroups(nextGroups);
      setEnabledFields({
        metric_group: false,
        unit: false,
        data_type: false,
        description: false
      });
      setEnumList([{ ...INIT_ENUM_ITEM }]);
      form.resetFields();
      setVisible(true);
    }
  }));

  const handleEnable = (field: BatchField, checked: boolean) => {
    setEnabledFields((prev) => ({ ...prev, [field]: checked }));
    if (!checked) {
      form.setFieldValue(field, undefined);
    }
  };

  const handleCancel = () => {
    setVisible(false);
    form.resetFields();
  };

  const validateEnumList = async () => {
    if (
      enumList.length &&
      enumList.some((item) =>
        Object.values(item).some((tex) => !tex && tex !== 0)
      )
    ) {
      return Promise.reject(new Error(t('common.valueValidate')));
    }
    return Promise.resolve();
  };

  const handleSubmit = async () => {
    const enabled = Object.entries(enabledFields)
      .filter(([, checked]) => checked)
      .map(([field]) => field as BatchField);
    if (!enabled.length) {
      message.warning(
        t('monitor.integrations.batchEditEmptyWarning', '请至少勾选一个要修改的字段')
      );
      return;
    }
    try {
      const values = await form.validateFields(enabled);
      if (enabledFields.data_type && values.data_type === 'Enum') {
        await validateEnumList();
      }
      if (
        enabledFields.unit &&
        !enabledFields.data_type &&
        hasEnumSelected
      ) {
        message.warning(
          t(
            'monitor.integrations.batchEditEnumUnitBlocked',
            '所选指标包含枚举类型，无法批量设置单位'
          )
        );
        return;
      }
      const payload: {
        ids: number[];
        monitor_plugin: number;
        metric_group?: number;
        unit?: string;
        data_type?: string;
        description?: string;
      } = {
        ids: metrics.map((item) => Number(item.id)),
        monitor_plugin: pluginId
      };
      if (enabledFields.metric_group) {
        payload.metric_group = Number(values.metric_group);
      }
      if (enabledFields.data_type) {
        payload.data_type = values.data_type;
        if (values.data_type === 'Enum') {
          payload.unit = JSON.stringify(enumList);
        } else if (enabledFields.unit) {
          payload.unit = resolvePersistCatalogUnitId(values.unit);
        } else if (hasEnumSelected) {
          payload.unit = 'none';
        }
      } else if (enabledFields.unit) {
        payload.unit = resolvePersistCatalogUnitId(values.unit);
      }
      if (enabledFields.description) {
        payload.description = values.description || '';
      }
      setConfirmLoading(true);
      await batchUpdateMonitorMetrics(payload);
      message.success(t('common.updateSuccess'));
      handleCancel();
      onSuccess();
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }
      const text =
        error instanceof Error ? error.message : t('common.operationFailed');
      message.error(text);
    } finally {
      setConfirmLoading(false);
    }
  };

  return (
    <OperateModal
      width={640}
      title={t('common.batchEdit')}
      visible={visible}
      onCancel={handleCancel}
      footer={
        <div>
          <Button
            className="mr-[10px]"
            type="primary"
            loading={confirmLoading}
            onClick={() => void handleSubmit()}
          >
            {t('common.confirm')}
          </Button>
          <Button onClick={handleCancel}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <p className="mb-3 text-[13px] text-[var(--color-text-3)]">
        {t(
          'monitor.integrations.metricBatchEditHint',
          '仅修改勾选的字段，未勾选的字段保持原值。已选 {count} 个指标。',
          { count: metrics.length }
        )}
      </p>
      <Form form={form} layout="vertical">
        <div className="flex items-start gap-2">
          <Checkbox
            className="mt-1"
            checked={enabledFields.metric_group}
            onChange={(event) =>
              handleEnable('metric_group', event.target.checked)
            }
          />
          <Form.Item
            className="min-w-0 flex-1"
            label={t('monitor.integrations.metricGroup')}
            name="metric_group"
            rules={
              enabledFields.metric_group
                ? [{ required: true, message: t('common.required') }]
                : []
            }
          >
            <ScriptMetricGroupSelect
              allowClear={false}
              disabled={!enabledFields.metric_group}
              placeholder={t('monitor.integrations.metricGroup')}
              objectId={monitorObject}
              pluginId={pluginId}
              groups={groups}
              onCreated={(created) => {
                setGroups((current) =>
                  current.some((group) => group.id === created.id)
                    ? current
                    : [...current, created]
                );
                onGroupListChange?.(created);
              }}
            />
          </Form.Item>
        </div>
        <div className="flex items-start gap-2">
          <Checkbox
            className="mt-1"
            checked={enabledFields.data_type}
            onChange={(event) =>
              handleEnable('data_type', event.target.checked)
            }
          />
          <Form.Item
            className="min-w-0 flex-1"
            label={t('monitor.integrations.dataType')}
            name="data_type"
            rules={
              enabledFields.data_type
                ? [{ required: true, message: t('common.required') }]
                : []
            }
          >
            <Select disabled={!enabledFields.data_type}>
              <Option value="Number">{t('monitor.integrations.number')}</Option>
              <Option value="Enum">{t('monitor.integrations.enum')}</Option>
            </Select>
          </Form.Item>
        </div>
        <div className="flex items-start gap-2">
          <Checkbox
            className="mt-1"
            checked={enabledFields.unit}
            disabled={enabledFields.data_type && dataType === 'Enum'}
            onChange={(event) => handleEnable('unit', event.target.checked)}
          />
          <Form.Item
            className="min-w-0 flex-1"
            label={t('common.unit')}
            name="unit"
            rules={
              enabledFields.unit &&
              !(enabledFields.data_type && dataType === 'Enum')
                ? [{ required: true, message: t('common.required') }]
                : []
            }
          >
            {enabledFields.data_type && dataType === 'Enum' ? (
              <ul>
                {enumList.map((item, index) => (
                  <li className="mb-[6px] flex items-center gap-2" key={index}>
                    <Input
                      className="w-[140px]"
                      placeholder={t('monitor.integrations.originalValue')}
                      value={item.id == null ? '' : String(item.id)}
                      onChange={(event) => {
                        const next = cloneDeep(enumList);
                        next[index].id = event.target.value
                          ? Number(event.target.value)
                          : null;
                        setEnumList(next);
                      }}
                    />
                    <Input
                      className="w-[140px]"
                      placeholder={t('monitor.integrations.mappedValue')}
                      value={item.name || ''}
                      onChange={(event) => {
                        const next = cloneDeep(enumList);
                        next[index].name = event.target.value;
                        setEnumList(next);
                      }}
                    />
                    <Button
                      icon={<PlusOutlined />}
                      onClick={() =>
                        setEnumList((current) => [
                          ...current,
                          { ...INIT_ENUM_ITEM }
                        ])
                      }
                    />
                    {index > 0 ? (
                      <Button
                        icon={<MinusOutlined />}
                        onClick={() =>
                          setEnumList((current) =>
                            current.filter((_, itemIndex) => itemIndex !== index)
                          )
                        }
                      />
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <Cascader
                allowClear
                disabled={!enabledFields.unit}
                className="w-full"
                options={unitOptions}
                displayRender={(labels) => {
                  const leaf = labels[labels.length - 1];
                  return leaf == null ? '' : String(leaf);
                }}
                showSearch={{
                  filter: (inputValue, path) => {
                    const needle = inputValue.trim().toLowerCase();
                    if (!needle) return true;
                    return path.some((option) => {
                      const label = String(option.label ?? '').toLowerCase();
                      const extra = String(
                        (option as { searchText?: string }).searchText ?? ''
                      ).toLowerCase();
                      return label.includes(needle) || extra.includes(needle);
                    });
                  }
                }}
              />
            )}
          </Form.Item>
        </div>
        <div className="flex items-start gap-2">
          <Checkbox
            className="mt-1"
            checked={enabledFields.description}
            onChange={(event) =>
              handleEnable('description', event.target.checked)
            }
          />
          <Form.Item
            className="min-w-0 flex-1"
            label={t('common.descripition')}
            name="description"
          >
            <Input.TextArea
              rows={3}
              disabled={!enabledFields.description}
              placeholder={t('common.descripition')}
            />
          </Form.Item>
        </div>
      </Form>
    </OperateModal>
  );
});

MetricBatchEditModal.displayName = 'MetricBatchEditModal';
export default MetricBatchEditModal;
