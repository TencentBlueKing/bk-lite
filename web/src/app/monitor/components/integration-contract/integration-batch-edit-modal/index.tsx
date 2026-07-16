import React, { forwardRef, useImperativeHandle, useState } from 'react';
import {
  Form,
  Checkbox,
  Input,
  InputNumber,
  Select,
  message,
} from 'antd';
import { useTranslation } from '@/utils/i18n';
import GroupSelect from '@/components/group-tree-select';
import AuthSecretField from '@/components/auth-secret-field';
import {
  createPasswordSecretFieldProps,
  createPrivateKeySecretFieldProps,
} from '@/components/auth-secret-field/presets';
import OperateFormModal from '@/components/operate-form-modal';

export interface IntegrationBatchEditColumnConfig {
  name: string;
  label: React.ReactNode;
  type: 'select' | 'input' | 'group_select' | 'inputNumber' | 'password' | 'auth_input';
  required?: boolean;
  enable_row_filter?: boolean;
  widget_props?: {
    mode?: 'multiple';
    placeholder?: string;
    options?: { label: string; value: unknown }[];
    min?: number;
    max?: number;
    precision?: number;
    addonAfter?: React.ReactNode;
    disabled?: boolean;
  };
  options?: { label: string; value: unknown }[];
}

export interface IntegrationBatchEditModalConfig {
  columns: IntegrationBatchEditColumnConfig[];
  selectedRows: unknown[];
  nodeList?: { label: string; value: unknown }[];
  groupList?: { label: string; value: unknown }[];
  title?: React.ReactNode;
  hideFieldToggles?: boolean;
  preEnabledFields?: string[];
  initialAuthType?: string;
  emptyWarningMessage?: React.ReactNode;
}

export interface IntegrationBatchEditModalRef {
  showModal: (config: IntegrationBatchEditModalConfig) => void;
}

interface IntegrationBatchEditModalProps {
  onSuccess: (editedFields: Record<string, unknown>) => void;
}

const IntegrationBatchEditModal = forwardRef<
  IntegrationBatchEditModalRef,
  IntegrationBatchEditModalProps
>(({ onSuccess }, ref) => {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [columns, setColumns] = useState<IntegrationBatchEditColumnConfig[]>([]);
  const [nodeList, setNodeList] = useState<{ label: string; value: unknown }[]>([]);
  const [enabledFields, setEnabledFields] = useState<Record<string, boolean>>({});
  const [title, setTitle] = useState<React.ReactNode>();
  const [hideFieldToggles, setHideFieldToggles] = useState(false);
  const [authTypeValue, setAuthTypeValue] = useState<string | undefined>();
  const [uploadedFileName, setUploadedFileName] = useState<string | undefined>();
  const [emptyWarningMessage, setEmptyWarningMessage] = useState<React.ReactNode>();

  useImperativeHandle(ref, () => ({
    showModal: (config) => {
      setColumns(config.columns || []);
      setNodeList(config.nodeList || []);
      setEnabledFields(
        (config.preEnabledFields || []).reduce<Record<string, boolean>>(
          (nextEnabledFields, fieldName) => ({
            ...nextEnabledFields,
            [fieldName]: true,
          }),
          {},
        ),
      );
      setTitle(config.title);
      setHideFieldToggles(config.hideFieldToggles === true);
      setAuthTypeValue(config.initialAuthType);
      setUploadedFileName(undefined);
      setEmptyWarningMessage(config.emptyWarningMessage);
      form.resetFields();
      setOpen(true);
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

  const renderFormItem = (column: IntegrationBatchEditColumnConfig) => {
    const isEnabled = hideFieldToggles || enabledFields[column.name];
    const isNodeField = column.enable_row_filter === true;
    const isPasswordField = column.name === 'password' || column.type === 'auth_input';
    const needAuthType = isPasswordField && !authTypeValue;
    const fieldDisabled = column.widget_props?.disabled === true || (isPasswordField && needAuthType);
    const isDisabled = isNodeField || !isEnabled;
    let widget: React.ReactNode;

    switch (column.type) {
      case 'input':
        widget = (
          <Input
            disabled={isDisabled}
            placeholder={column.widget_props?.placeholder || ''}
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
            placeholder={column.widget_props?.placeholder || ''}
            addonAfter={column.widget_props?.addonAfter}
          />
        );
        break;
      case 'select':
        widget = (
          <Select
            disabled={isDisabled}
            showSearch
            optionFilterProp="label"
            placeholder={column.widget_props?.placeholder || ''}
            options={column.name === 'node_ids' ? nodeList : column.options || []}
            allowClear={column.name === 'auth_type'}
            onChange={(value) => {
              if (column.name === 'auth_type') {
                setAuthTypeValue(value as string | undefined);
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
            placeholder={column.widget_props?.placeholder || ''}
          />
        );
        break;
      case 'password':
        widget = (
          <AuthSecretField
            {...createPasswordSecretFieldProps({
              passwordDisabled: isDisabled,
              passwordPlaceholder: column.widget_props?.placeholder || '',
            })}
          />
        );
        break;
      case 'auth_input':
        widget =
          authTypeValue === 'private_key' ? (
            <AuthSecretField
              {...createPrivateKeySecretFieldProps({
                fileName: uploadedFileName,
                onPrivateKeyClear: () => {
                  setUploadedFileName(undefined);
                  form.setFieldValue(column.name, undefined);
                  form.setFieldValue('private_key', undefined);
                },
                onPrivateKeyLoaded: (content, fileName) => {
                  form.setFieldValue('private_key', content);
                  form.setFieldValue(column.name, '');
                  setUploadedFileName(fileName);
                },
              })}
            />
          ) : (
            <AuthSecretField
              {...createPasswordSecretFieldProps({
                passwordDisabled: isDisabled,
                passwordPlaceholder: column.widget_props?.placeholder || '',
              })}
            />
          );
        break;
      default:
        widget = (
          <Input
            disabled={isDisabled}
            placeholder={column.widget_props?.placeholder || ''}
          />
        );
    }

    return (
      <div key={column.name} style={{ width: 'calc(50% - 8px)', marginBottom: 16 }}>
        {hideFieldToggles ? (
          <div style={{ marginBottom: 8, fontWeight: 500 }}>{column.label}</div>
        ) : (
          <div style={{ marginBottom: 8 }}>
            <Checkbox
              checked={isEnabled}
              onChange={(e) => handleCheckboxChange(column.name, e.target.checked)}
              disabled={isNodeField || fieldDisabled}
            >
              {column.label}
            </Checkbox>
          </div>
        )}
        <Form.Item name={column.name} style={{ marginBottom: 0 }}>
          {widget}
        </Form.Item>
      </div>
    );
  };

  const handleSubmit = () => {
    const values = form.getFieldsValue();
    const editedFields: Record<string, unknown> = {};

    Object.keys(values).forEach((key) => {
      const value = values[key];
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

    if (Object.keys(editedFields).length === 0) {
      message.warning(
        emptyWarningMessage || t('monitor.integrations.batchEditEmptyWarning'),
      );
      return;
    }

    onSuccess(editedFields);
    setOpen(false);
  };

  const handleCancel = () => {
    setOpen(false);
    setEnabledFields({});
    setTitle(undefined);
    setHideFieldToggles(false);
    setAuthTypeValue(undefined);
    setUploadedFileName(undefined);
    form.resetFields();
  };

  return (
    <OperateFormModal
      title={title || t('common.batchEdit')}
      open={open}
      onCancel={handleCancel}
      width={600}
      confirmText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onConfirm={handleSubmit}
    >
      <Form form={form} layout="vertical">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          {columns.map((column) => renderFormItem(column))}
        </div>
      </Form>
    </OperateFormModal>
  );
});

IntegrationBatchEditModal.displayName = 'IntegrationBatchEditModal';

export default IntegrationBatchEditModal;
