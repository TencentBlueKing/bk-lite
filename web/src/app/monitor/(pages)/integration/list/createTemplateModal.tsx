'use client';

import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useState
} from 'react';
import { Button, Form, Input, Radio, Select, Alert, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import { ModalRef, ObjectItem } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';

const OS_MONITOR_OBJECT_TYPE = 'OS';

const isOsMonitorObjectType = (type: unknown) =>
  String(type || '').trim().toUpperCase() === OS_MONITOR_OBJECT_TYPE;

interface CreateTemplateModalProps {
  objects: ObjectItem[];
  onSubmit: (
    values: Record<string, any>,
    mode: 'add' | 'edit',
    id?: number
  ) => Promise<void>;
}

const CreateTemplateModal = forwardRef<ModalRef, CreateTemplateModalProps>(
  ({ objects, onSubmit }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState(false);
    const [loading, setLoading] = useState(false);
    const [form] = Form.useForm();
    const [templateId, setTemplateId] = useState<number | undefined>(undefined);
    const [mode, setMode] = useState<'add' | 'edit'>('add');
    const [selectedObjectType, setSelectedObjectType] = useState<
      string | undefined
    >(undefined);
    const templateType = Form.useWatch('template_type', form);

    const isScriptTemplate = templateType === 'script';

    const objectTypeOptions = useMemo(() => {
      const typeMap = new Map<string, string>();

      objects.forEach((item) => {
        if (!typeMap.has(item.type)) {
          typeMap.set(item.type, item.display_type || item.type);
        }
      });

      return Array.from(typeMap.entries()).map(([value, label]) => ({
        value,
        label,
        disabled: isScriptTemplate && !isOsMonitorObjectType(value)
      }));
    }, [objects, isScriptTemplate]);

    const monitorObjectOptions = useMemo(
      () =>
        objects
          .filter((item) => {
            if (isScriptTemplate) {
              return isOsMonitorObjectType(item.type);
            }
            return !selectedObjectType || item.type === selectedObjectType;
          })
          .map((item) => ({
            value: item.id,
            label: item.display_name || item.name
          })),
      [objects, selectedObjectType, isScriptTemplate]
    );

    const lockScriptMonitorObject = () => {
      if (mode !== 'add') {
        return false;
      }
      let clearedObject = false;
      const currentType = form.getFieldValue('monitor_object_type');
      if (!isOsMonitorObjectType(currentType)) {
        form.setFieldValue('monitor_object_type', OS_MONITOR_OBJECT_TYPE);
        setSelectedObjectType(OS_MONITOR_OBJECT_TYPE);
      }
      const currentObject = form.getFieldValue('monitor_object');
      const objectOk = objects.some(
        (item) => item.id === currentObject && isOsMonitorObjectType(item.type)
      );
      if (currentObject && !objectOk) {
        form.setFieldValue('monitor_object', undefined);
        clearedObject = true;
      }
      return clearedObject;
    };

    useEffect(() => {
      if (!visible || !isScriptTemplate) {
        return;
      }
      const clearedObject = lockScriptMonitorObject();
      void form
        .validateFields(
          clearedObject
            ? ['monitor_object_type', 'monitor_object']
            : ['monitor_object_type']
        )
        .catch(() => undefined);
    }, [visible, isScriptTemplate, mode, objects, form]);

    useImperativeHandle(ref, () => ({
      showModal: ({ form: initialForm = {}, type }) => {
        const initialMonitorObject =
          initialForm?.monitor_object?.[0] ||
          initialForm?.parent_monitor_object;
        const targetObject = objects.find(
          (item) => item.id === initialMonitorObject
        );

        setVisible(true);
        setMode(type === 'edit' ? 'edit' : 'add');
        setTemplateId(initialForm?.id);
        setSelectedObjectType(targetObject?.type);
        form.resetFields();
        form.setFieldsValue({
          monitor_object_type: targetObject?.type,
          monitor_object: initialMonitorObject,
          display_name: initialForm?.display_name,
          template_id: initialForm?.template_id,
          description: initialForm?.description,
          template_type:
            initialForm?.template_type === 'pull'
              ? 'pull'
              : initialForm?.template_type === 'snmp'
                ? 'snmp'
                : initialForm?.template_type === 'script'
                  ? 'script'
                  : 'api'
        });
      }
    }));

    const handleObjectTypeChange = (value: string) => {
      setSelectedObjectType(value);
      form.setFieldValue('monitor_object', undefined);
    };

    const handleSubmit = async () => {
      if (loading) {
        return;
      }
      const values = await form.validateFields();
      setLoading(true);
      try {
        await onSubmit(
          {
            display_name: values.display_name,
            template_id: values.template_id,
            description: values.description,
            name: values.template_id,
            monitor_object: [values.monitor_object],
            template_type: values.template_type
          },
          mode,
          templateId
        );
        setVisible(false);
      } catch (error: any) {
        message.error(
          error?.message || t('common.operationFailed')
        );
      } finally {
        setLoading(false);
      }
    };

    return (
      <OperateModal
        width={640}
        title={mode === 'edit' ? t('common.edit') : t('common.add')}
        open={visible}
        onCancel={() => setVisible(false)}
        footer={
          <div>
            <Button
              className="mr-[10px]"
              type="primary"
              loading={loading}
              disabled={loading}
              onClick={handleSubmit}
            >
              {t('common.confirm')}
            </Button>
            <Button onClick={() => setVisible(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        }
      >
        <Form
          form={form}
          layout="vertical"
          onValuesChange={(changed) => {
            if (changed.template_type !== 'script') {
              return;
            }
            const clearedObject = lockScriptMonitorObject();
            void form
              .validateFields(
                clearedObject
                  ? ['monitor_object_type', 'monitor_object']
                  : ['monitor_object_type']
              )
              .catch(() => undefined);
          }}
        >
          <Form.Item
            label={t('monitor.integrations.templateType')}
            name="template_type"
          >
            <Radio.Group>
              <Radio value="api">API</Radio>
              <Radio value="pull">PULL</Radio>
              <Radio value="snmp">SNMP</Radio>
              <Radio value="script">{t('monitor.integrations.script')}</Radio>
            </Radio.Group>
          </Form.Item>
          {templateType === 'pull' && (
            <Alert
              message={t('monitor.integrations.pullTemplateHint')}
              type="warning"
              showIcon
              className="mb-[16px]"
            />
          )}
          {templateType === 'snmp' && (
            <Alert
              message={t('monitor.integrations.snmpTemplateHint')}
              type="info"
              showIcon
              className="mb-[16px]"
            />
          )}
          {isScriptTemplate && (
            <Alert
              message={t('monitor.integrations.scriptTemplateHint')}
              type="info"
              showIcon
              className="mb-[16px]"
            />
          )}
          <Form.Item
            label={t('monitor.integrations.monitorObjectType')}
            name="monitor_object_type"
            dependencies={['template_type']}
            rules={[
              { required: true, message: t('common.required') },
              {
                validator: async (_, value) => {
                  if (
                    form.getFieldValue('template_type') === 'script' &&
                    !isOsMonitorObjectType(value)
                  ) {
                    throw new Error(
                      t(
                        'monitor.integrations.scriptTemplateOsOnly',
                        '仅操作系统可创建脚本采集模板'
                      )
                    );
                  }
                }
              }
            ]}
          >
            <Select
              disabled={mode === 'edit'}
              options={objectTypeOptions}
              onChange={handleObjectTypeChange}
              placeholder={t('monitor.integrations.selectMonitorObjectType')}
            />
          </Form.Item>
          <Form.Item
            label={t('monitor.integrations.monitorObject')}
            name="monitor_object"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Select
              disabled={mode === 'edit'}
              options={monitorObjectOptions}
              placeholder={t('monitor.integrations.selectMonitorObject')}
            />
          </Form.Item>
          <Form.Item
            label={t('monitor.integrations.templateName')}
            name="display_name"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label={t('monitor.integrations.templateId')}
            name="template_id"
            rules={[{ required: true, message: t('common.required') }]}
          >
            <Input disabled={mode === 'edit'} />
          </Form.Item>
          <Form.Item
            label={t('monitor.integrations.templateDescription')}
            name="description"
          >
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);

CreateTemplateModal.displayName = 'CreateTemplateModal';

export default CreateTemplateModal;
