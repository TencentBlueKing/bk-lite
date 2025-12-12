import React, { useState, forwardRef, useImperativeHandle } from 'react';
import {
  Form,
  Checkbox,
  Input,
  InputNumber,
  Select,
  Button,
  message,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import GroupSelect from '@/components/group-tree-select';
import OperateModal from '@/app/monitor/components/operate-drawer';

interface ModalRef {
  showModal: (config: {
    columns: any[];
    selectedRows: any[];
    groupList?: any[];
  }) => void;
}

interface BatchEditModalProps {
  onSuccess: (editedFields: any) => void;
}

const BatchEditModal = forwardRef<ModalRef, BatchEditModalProps>(
  ({ onSuccess }, ref) => {
    const { t } = useTranslation();
    const [form] = Form.useForm();
    const [visible, setVisible] = useState(false);
    const [columns, setColumns] = useState<any[]>([]);
    const [enabledFields, setEnabledFields] = useState<{
      [key: string]: boolean;
    }>({});

    useImperativeHandle(ref, () => ({
      showModal: (config) => {
        setColumns(config.columns || []);
        setEnabledFields({});
        form.resetFields();
        setVisible(true);
      },
    }));

    const handleCheckboxChange = (fieldName: string, checked: boolean) => {
      setEnabledFields((prev) => ({
        ...prev,
        [fieldName]: checked,
      }));
      if (!checked) {
        form.setFieldValue(fieldName, undefined);
      }
    };

    const renderFormItem = (column: any) => {
      const isEnabled = enabledFields[column.name];
      const isDisabled = !isEnabled;
      const fieldDisabled = column.widget_props?.disabled === true;
      let widget = null;

      switch (column.type) {
        case 'input':
          widget = (
            <Input
              disabled={isDisabled}
              placeholder={column.widget_props?.placeholder}
            />
          );
          break;
        case 'password':
          widget = (
            <Input.Password
              disabled={isDisabled}
              placeholder={column.widget_props?.placeholder}
            />
          );
          break;
        case 'inputNumber':
          widget = (
            <InputNumber
              disabled={isDisabled}
              style={{ width: '100%' }}
              min={column.widget_props?.min}
              precision={column.widget_props?.precision}
              placeholder={column.widget_props?.placeholder}
              addonAfter={column.widget_props?.addonAfter}
            />
          );
          break;
        case 'select':
          widget = (
            <Select
              disabled={isDisabled}
              placeholder={column.widget_props?.placeholder}
              options={column.options || []}
            />
          );
          break;
        case 'group_select':
          widget = (
            <GroupSelect
              disabled={isDisabled}
              placeholder={column.widget_props?.placeholder}
            />
          );
          break;
        default:
          widget = (
            <Input
              disabled={isDisabled}
              placeholder={column.widget_props?.placeholder}
            />
          );
      }

      return (
        <div
          key={column.name}
          style={{ width: 'calc(50% - 8px)', marginBottom: 16 }}
        >
          <div style={{ marginBottom: 8 }}>
            <Checkbox
              checked={isEnabled}
              disabled={fieldDisabled}
              onChange={(e) =>
                handleCheckboxChange(column.name, e.target.checked)
              }
            >
              {column.label}
            </Checkbox>
          </div>
          <Form.Item name={column.name} style={{ marginBottom: 0 }}>
            {widget}
          </Form.Item>
        </div>
      );
    };

    const handleSubmit = async () => {
      try {
        const values = form.getFieldsValue();
        // 收集所有非空的字段值
        const editedFields: any = {};
        Object.keys(values).forEach((key) => {
          const value = values[key];
          // 检查值是否为空（undefined、null、空字符串、空数组）
          if (
            value !== undefined &&
            value !== null &&
            value !== '' &&
            !(Array.isArray(value) && value.length === 0)
          ) {
            editedFields[key] = value;
          }
        });
        // 如果所有字段都为空，提示用户
        if (Object.keys(editedFields).length === 0) {
          message.warning(
            t('node-manager.cloudregion.integrations.batchEditEmptyWarning')
          );
          return;
        }
        onSuccess(editedFields);
        setVisible(false);
      } catch (error) {
        console.error('Form validation failed:', error);
      }
    };

    const handleCancel = () => {
      setVisible(false);
      setEnabledFields({});
      form.resetFields();
    };

    return (
      <OperateModal
        title={t('common.batchEdit')}
        visible={visible}
        onClose={handleCancel}
        width={600}
        footer={
          <div>
            <Button className="mr-[10px]" type="primary" onClick={handleSubmit}>
              {t('common.confirm')}
            </Button>
            <Button onClick={handleCancel}>{t('common.cancel')}</Button>
          </div>
        }
      >
        <Form form={form} layout="vertical">
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            {columns.map((column) => renderFormItem(column))}
          </div>
        </Form>
      </OperateModal>
    );
  }
);

BatchEditModal.displayName = 'BatchEditModal';

export default BatchEditModal;
