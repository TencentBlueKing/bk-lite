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
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

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
    const [authTypeValue, setAuthTypeValue] = useState<string | undefined>();
    const [uploadedFileName, setUploadedFileName] = useState<
      string | undefined
    >();

    useImperativeHandle(ref, () => ({
      showModal: (config) => {
        setColumns(config.columns || []);
        setEnabledFields({});
        setAuthTypeValue(undefined);
        setUploadedFileName(undefined);
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
      // password/auth_input字段额外检查是否依赖auth_type
      const isPasswordField =
        column.name === 'password' || column.type === 'auth_input';
      const needAuthType = isPasswordField && !authTypeValue;
      const fieldDisabled =
        column.widget_props?.disabled === true ||
        (isPasswordField && needAuthType);
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
        case 'auth_input':
          if (authTypeValue === 'private_key') {
            widget = uploadedFileName ? (
              <div className="inline-flex items-center gap-2 text-[var(--color-text-1)] max-w-full group">
                <EllipsisWithTooltip
                  text={uploadedFileName}
                  className="overflow-hidden text-ellipsis whitespace-nowrap"
                />
                <span
                  className="cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                  style={{
                    fontSize: 16,
                    color: 'var(--color-primary)',
                    fontWeight: 'bold',
                  }}
                  onClick={() => {
                    setUploadedFileName(undefined);
                    form.setFieldValue(column.name, undefined);
                    form.setFieldValue('private_key', undefined);
                  }}
                  title={t('common.delete')}
                >
                  ×
                </span>
              </div>
            ) : (
              <Button
                disabled={isDisabled}
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.onchange = (e: any) => {
                    const file = e.target.files[0];
                    if (file) {
                      const reader = new FileReader();
                      reader.onload = (event) => {
                        const content = event.target?.result as string;
                        // 将秘钥内容存储到private_key字段，清空password字段
                        form.setFieldValue('private_key', content);
                        form.setFieldValue(column.name, '');
                        setUploadedFileName(file.name);
                      };
                      reader.readAsText(file);
                    }
                  };
                  input.click();
                }}
              >
                {t('node-manager.cloudregion.node.uploadPrivateKey')}
              </Button>
            );
          } else {
            widget = (
              <Input.Password
                disabled={isDisabled}
                placeholder={column.widget_props?.placeholder}
              />
            );
          }
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
              options={column.widget_props?.options || []}
              allowClear={column.name === 'auth_type'}
              onChange={(value) => {
                if (column.name === 'auth_type') {
                  setAuthTypeValue(value);
                  if (!value) {
                    setEnabledFields((prev) => ({
                      ...prev,
                      password: false,
                    }));
                    form.setFieldValue('password', undefined);
                  }
                }
              }}
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
        if (uploadedFileName) {
          editedFields.key_file_name = uploadedFileName;
          const privateKeyValue = form.getFieldValue('private_key');
          if (privateKeyValue) {
            editedFields.private_key = privateKeyValue;
          }
        }
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
      setAuthTypeValue(undefined);
      setUploadedFileName(undefined);
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
