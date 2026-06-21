'use client';

import React, { useEffect, useState } from 'react';
import { Drawer, Form, Input, Select, Button, Space, message } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSettingApi } from '@/app/alarm/api/settings';
import { EnrichmentRuleListItem } from '@/app/alarm/types/settings';

interface OperateModalProps {
  open: boolean;
  onClose: () => void;
  currentRow?: EnrichmentRuleListItem | null;
  onSuccess?: () => void;
}

const OperateModal: React.FC<OperateModalProps> = ({
  open,
  onClose,
  currentRow,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { createEnrichment, updateEnrichment } = useSettingApi();
  const [form] = Form.useForm();
  const [submitLoading, setSubmitLoading] = useState(false);
  const isEdit = !!currentRow;

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  useEffect(() => {
    if (!open) return;
    if (isEdit && currentRow) {
      form.setFieldsValue({
        name: currentRow.name,
        provider_type: currentRow.provider_type || 'cmdb',
        namespace: currentRow.namespace,
        on_multiple: currentRow.on_multiple || 'first',
        input_binding: Object.entries(currentRow.input_binding || {}).map(
          ([param, field]) => ({ param, field })
        ),
        output_projection: (currentRow.output_projection || []).map((p) => ({
          source: p.source,
          as: p.as || '',
        })),
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        provider_type: 'cmdb',
        on_multiple: 'first',
        input_binding: [
          { param: 'model_id', field: 'resource_type' },
          { param: '_id', field: 'resource_id' },
        ],
        output_projection: [],
      });
    }
  }, [open, isEdit, currentRow, form]);

  const onFinish = async (values: any) => {
    setSubmitLoading(true);
    try {
      const input_binding: Record<string, string> = {};
      (values.input_binding || []).forEach((r: any) => {
        if (r.param && r.field) input_binding[r.param] = r.field;
      });
      const output_projection = (values.output_projection || [])
        .filter((r: any) => r.source)
        .map((r: any) =>
          r.as ? { source: r.source, as: r.as } : { source: r.source }
        );

      const payload = {
        name: values.name,
        is_active: currentRow?.is_active ?? true,
        provider_type: values.provider_type,
        namespace: values.namespace || '',
        match_rules: currentRow?.match_rules || [],
        provider_config: currentRow?.provider_config || {},
        input_binding,
        output_projection,
        on_multiple: values.on_multiple,
      };

      if (isEdit && currentRow) {
        await updateEnrichment(currentRow.id, payload);
      } else {
        await createEnrichment(payload);
      }
      message.success(t('alarmCommon.successOperate'));
      handleClose();
      onSuccess?.();
    } catch {
      message.error(t('alarmCommon.operateFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  return (
    <Drawer
      title={
        isEdit
          ? t('common.edit') + (currentRow ? ` - ${currentRow.name}` : '')
          : t('common.addNew')
      }
      placement="right"
      width={720}
      open={open}
      onClose={handleClose}
      maskClosable={false}
      footer={
        <div style={{ textAlign: 'right' }}>
          <Button
            type="primary"
            loading={submitLoading}
            onClick={() => form.submit()}
          >
            {t('common.confirm')}
          </Button>
          <Button style={{ marginLeft: 8 }} onClick={handleClose}>
            {t('common.cancel')}
          </Button>
        </div>
      }
    >
      <Form form={form} layout="vertical" onFinish={onFinish}>
        <Form.Item
          name="name"
          label={t('settings.enrichmentName')}
          rules={[{ required: true, message: t('common.inputTip') }]}
        >
          <Input maxLength={100} placeholder={t('common.inputTip')} />
        </Form.Item>

        <Form.Item
          name="provider_type"
          label={t('settings.enrichmentProvider')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Select options={[{ label: 'CMDB', value: 'cmdb' }]} />
        </Form.Item>

        <Form.Item name="namespace" label={t('settings.enrichmentNamespace')}>
          <Input placeholder="cmdb" />
        </Form.Item>

        <Form.Item label={t('settings.enrichmentInputBinding')} required>
          <Form.List name="input_binding">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key} align="baseline" className="flex mb-2">
                    <Form.Item
                      {...rest}
                      name={[name, 'param']}
                      rules={[{ required: true, message: t('common.inputTip') }]}
                      noStyle
                    >
                      <Input
                        placeholder={t('settings.enrichmentBindParam')}
                        style={{ width: 280 }}
                      />
                    </Form.Item>
                    <Form.Item
                      {...rest}
                      name={[name, 'field']}
                      rules={[{ required: true, message: t('common.inputTip') }]}
                      noStyle
                    >
                      <Input
                        placeholder={t('settings.enrichmentBindField')}
                        style={{ width: 280 }}
                      />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  onClick={() => add()}
                  icon={<PlusOutlined />}
                  block
                >
                  {t('common.addNew')}
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>

        <Form.Item label={t('settings.enrichmentOutputProjection')}>
          <Form.List name="output_projection">
            {(fields, { add, remove }) => (
              <>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key} align="baseline" className="flex mb-2">
                    <Form.Item
                      {...rest}
                      name={[name, 'source']}
                      rules={[{ required: true, message: t('common.inputTip') }]}
                      noStyle
                    >
                      <Input
                        placeholder={t('settings.enrichmentProjSource')}
                        style={{ width: 280 }}
                      />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, 'as']} noStyle>
                      <Input
                        placeholder={t('settings.enrichmentProjAs')}
                        style={{ width: 280 }}
                      />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(name)} />
                  </Space>
                ))}
                <Button
                  type="dashed"
                  onClick={() => add()}
                  icon={<PlusOutlined />}
                  block
                >
                  {t('common.addNew')}
                </Button>
              </>
            )}
          </Form.List>
        </Form.Item>

        <Form.Item
          name="on_multiple"
          label={t('settings.enrichmentOnMultiple')}
          rules={[{ required: true, message: t('common.selectTip') }]}
        >
          <Select
            options={[
              { label: t('settings.onMultipleFirst'), value: 'first' },
              { label: t('settings.onMultipleMerge'), value: 'merge' },
              { label: t('settings.onMultipleList'), value: 'list' },
            ]}
          />
        </Form.Item>
      </Form>
    </Drawer>
  );
};

export default OperateModal;
