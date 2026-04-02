'use client';

import React, {
  forwardRef,
  useImperativeHandle,
  useMemo,
  useState
} from 'react';
import { Button, Form, Input, Radio, Select } from 'antd';
import OperateModal from '@/components/operate-modal';
import { ModalRef, ObjectItem } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';

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

    const objectTypeOptions = useMemo(() => {
      const typeMap = new Map<string, string>();

      objects.forEach((item) => {
        if (!typeMap.has(item.type)) {
          typeMap.set(item.type, item.display_type || item.type);
        }
      });

      return Array.from(typeMap.entries()).map(([value, label]) => ({
        value,
        label
      }));
    }, [objects]);

    const monitorObjectOptions = useMemo(
      () =>
        objects
          .filter(
            (item) => !selectedObjectType || item.type === selectedObjectType
          )
          .map((item) => ({
            value: item.id,
            label: item.display_name || item.name
          })),
      [objects, selectedObjectType]
    );

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
          template_type: initialForm?.template_type === 'pull' ? 'pull' : 'api'
        });
      }
    }));

    const handleObjectTypeChange = (value: string) => {
      setSelectedObjectType(value);
      form.setFieldValue('monitor_object', undefined);
    };

    const handleSubmit = async () => {
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
        <Form form={form} layout="vertical">
          <Form.Item
            label={t('monitor.integrations.monitorObjectType')}
            name="monitor_object_type"
            rules={[{ required: true, message: t('common.required') }]}
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
            label={t('monitor.integrations.templateType')}
            name="template_type"
          >
            <Radio.Group>
              <Radio value="api">API</Radio>
              <Radio value="pull">PULL</Radio>
              <Radio value="snmp" disabled>
                SNMP
              </Radio>
            </Radio.Group>
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
