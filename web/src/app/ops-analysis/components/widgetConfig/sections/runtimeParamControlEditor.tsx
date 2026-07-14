import React, { useEffect, useMemo } from 'react';
import {
  Button,
  Form,
  Input,
  Select,
  Space,
  Switch,
  type FormInstance,
} from 'antd';
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  PlusOutlined,
} from '@ant-design/icons';

import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import {
  getWidgetRuntimeParamCandidates,
  shouldClearUnavailableRuntimeParamControl,
} from '@/app/ops-analysis/utils/runtimeParamControl';
import type { WidgetConfigFormValues } from '../utils/submitConfig';

interface RuntimeParamControlEditorProps {
  form: FormInstance<WidgetConfigFormValues>;
  selectedDataSource?: DatasourceItem;
  t: (key: string) => string;
}

export const RuntimeParamControlEditor: React.FC<
  RuntimeParamControlEditorProps
> = ({ form, selectedDataSource, t }) => {
  const candidates = useMemo(
    () => getWidgetRuntimeParamCandidates(selectedDataSource?.params || []),
    [selectedDataSource?.params],
  );
  const enabled = Form.useWatch('runtimeParamControlEnabled', form);
  const options =
    Form.useWatch(['runtimeParamControl', 'options'], form) || [];
  const hasConfiguredControl = Boolean(
    Form.useWatch('runtimeParamControl', form),
  );
  const dataSourceResolved = Boolean(selectedDataSource);
  const singleCandidateName =
    candidates.length === 1 ? candidates[0].name : undefined;

  useEffect(() => {
    if (
      !shouldClearUnavailableRuntimeParamControl(
        selectedDataSource?.params,
        dataSourceResolved,
        enabled,
        hasConfiguredControl,
      )
    ) {
      return;
    }

    form.setFieldsValue({
      runtimeParamControlEnabled: false,
      runtimeParamControl: undefined,
    });
  }, [
    dataSourceResolved,
    enabled,
    form,
    hasConfiguredControl,
    selectedDataSource?.params,
  ]);

  useEffect(() => {
    if (
      enabled &&
      singleCandidateName &&
      !form.getFieldValue(['runtimeParamControl', 'paramName'])
    ) {
      form.setFieldValue(
        ['runtimeParamControl', 'paramName'],
        singleCandidateName,
      );
    }
  }, [enabled, form, singleCandidateName]);

  if (candidates.length === 0) return null;

  const handleEnabledChange = (checked: boolean) => {
    if (!checked) {
      form.setFieldValue('runtimeParamControl', undefined);
      return;
    }

    form.setFieldValue(
      ['runtimeParamControl', 'controlType'],
      'segmented',
    );
    if (singleCandidateName) {
      form.setFieldValue(
        ['runtimeParamControl', 'paramName'],
        singleCandidateName,
      );
    }
  };

  const defaultOptions = options
    .filter(
      (item) =>
        item &&
        String(item.label || '').trim() &&
        (typeof item.value === 'number' || String(item.value || '').trim()),
    )
    .map((item) => ({ label: item.label, value: item.value }));

  return (
    <div className="mt-6 border-t border-(--color-border-2) pt-4">
      <div className="mb-4 font-medium">
        {t('dashboard.runtimeParamControl')}
      </div>
      <Form.Item
        label={t('dashboard.runtimeParamControlEnabled')}
        name="runtimeParamControlEnabled"
        valuePropName="checked"
      >
        <Switch onChange={handleEnabledChange} />
      </Form.Item>

      {enabled ? (
        <>
          <Form.Item
            label={t('dashboard.runtimeParamName')}
            name={['runtimeParamControl', 'paramName']}
          >
            <Select
              options={candidates.map((item) => ({
                label: item.alias_name || item.name,
                value: item.name,
              }))}
            />
          </Form.Item>
          <Form.Item
            name={['runtimeParamControl', 'controlType']}
            hidden
          >
            <Input />
          </Form.Item>

          <Form.Item label={t('dashboard.runtimeParamOptions')}>
            <Form.List name={['runtimeParamControl', 'options']}>
              {(fields, { add, remove, move }) => (
                <Space direction="vertical" className="w-full" size={8}>
                  {fields.map((field, index) => (
                    <Space key={field.key} className="w-full" align="start">
                      <Form.Item
                        {...field}
                        name={[field.name, 'label']}
                        className="mb-0 flex-1"
                      >
                        <Input
                          placeholder={t('dashboard.runtimeParamOptionLabel')}
                        />
                      </Form.Item>
                      <Form.Item
                        {...field}
                        name={[field.name, 'value']}
                        className="mb-0 flex-1"
                      >
                        <Input
                          placeholder={t('dashboard.runtimeParamOptionValue')}
                        />
                      </Form.Item>
                      <Button
                        type="text"
                        icon={<ArrowUpOutlined />}
                        aria-label={t('dashboard.runtimeParamOptionMoveUp')}
                        disabled={index === 0}
                        onClick={() => move(index, index - 1)}
                      />
                      <Button
                        type="text"
                        icon={<ArrowDownOutlined />}
                        aria-label={t('dashboard.runtimeParamOptionMoveDown')}
                        disabled={index === fields.length - 1}
                        onClick={() => move(index, index + 1)}
                      />
                      <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        aria-label={t('dashboard.runtimeParamOptionDelete')}
                        onClick={() => remove(field.name)}
                      />
                    </Space>
                  ))}
                  <Button
                    type="dashed"
                    block
                    icon={<PlusOutlined />}
                    onClick={() => add({ label: '', value: '' })}
                  >
                    {t('dashboard.runtimeParamAddOption')}
                  </Button>
                </Space>
              )}
            </Form.List>
          </Form.Item>

          <Form.Item
            label={t('dashboard.runtimeParamDefault')}
            name={['runtimeParamControl', 'defaultValue']}
          >
            <Select options={defaultOptions} />
          </Form.Item>
        </>
      ) : null}
    </div>
  );
};
