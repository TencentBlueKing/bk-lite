'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useCallback,
} from 'react';
import { Input, Button, Form, Select, InputNumber } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import {
  ModalRef,
  SegmentedItem,
  TableDataItem,
} from '@/app/node-manager/types';
import { ControllerInstallFields } from '@/app/node-manager/types/cloudregion';
import { BATCH_FIELD_MAPS } from '@/app/node-manager/constants/cloudregion';
import { useTranslation } from '@/utils/i18n';
import { cloneDeep } from 'lodash';
const { Option } = Select;

interface ModalProps {
  onSuccess: (row: any) => void;
  config: {
    systemList: SegmentedItem[];
    groupList: SegmentedItem[];
  };
}

const BatchEditModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess, config: { systemList, groupList } }, ref) => {
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [groupForm, setGroupForm] = useState<TableDataItem>({});
    const [title, setTitle] = useState<string>('');
    const [field, setField] = useState<string>('os');
    const [authTypeValue, setAuthTypeValue] = useState<string | undefined>();
    const [uploadedFileName, setUploadedFileName] = useState<
      string | undefined
    >();

    useImperativeHandle(ref, () => ({
      showModal: ({ form, title, type, authType }) => {
        // 开启弹窗的交互
        const formData = cloneDeep(form || {});
        setGroupForm(formData);
        setGroupVisible(true);
        setField(type || 'os');
        setTitle(title || '');
        setAuthTypeValue(
          type === 'password' ? authType || 'password' : undefined
        );
        setUploadedFileName(undefined);
      },
    }));

    useEffect(() => {
      if (groupVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(groupForm);
      }
    }, [groupVisible, groupForm]);

    const renderFormItem = useCallback(() => {
      switch (field) {
        case 'password':
          if (authTypeValue === 'private_key') {
            return uploadedFileName ? (
              <div className="flex-1 relative group py-1 text-[var(--color-text-1)] truncate">
                <span
                  className="block overflow-hidden text-ellipsis whitespace-nowrap"
                  title={uploadedFileName}
                >
                  {uploadedFileName}
                </span>
                <span
                  className="absolute -top-1.5 right-0 cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{
                    fontSize: 16,
                    color: 'var(--color-primary)',
                    fontWeight: 'bold',
                  }}
                  onClick={() => {
                    setUploadedFileName(undefined);
                    formRef.current?.setFieldValue('id', undefined);
                    formRef.current?.setFieldValue('private_key', undefined);
                  }}
                  title={t('common.delete')}
                >
                  ×
                </span>
              </div>
            ) : (
              <Button
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.accept = '.txt';
                  input.onchange = (e: any) => {
                    const file = e.target.files[0];
                    if (file) {
                      const reader = new FileReader();
                      reader.onload = (event) => {
                        const content = event.target?.result as string;
                        formRef.current?.setFieldValue('private_key', content);
                        formRef.current?.setFieldValue('id', '');
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
          }
          return <Input.Password />;
        case 'os':
          return (
            <Select>
              {systemList.map((item: SegmentedItem) => (
                <Option key={item.value} value={item.value}>
                  {item.label}
                </Option>
              ))}
            </Select>
          );
        case 'organizations':
          return (
            <Select mode="multiple" maxTagCount="responsive">
              {groupList.map((item: SegmentedItem) => (
                <Option key={item.value} value={item.value}>
                  {item.label}
                </Option>
              ))}
            </Select>
          );
        case 'port':
          return <InputNumber min={1} precision={0} className="w-full" />;
        default:
          return <Input />;
      }
    }, [field, authTypeValue, uploadedFileName, t, systemList, groupList]);

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const formData: TableDataItem = {};
        formData.field = field;
        if (field === 'password' && authTypeValue === 'private_key') {
          formData.value = '';
          formData.key_file_name = uploadedFileName;
          formData.private_key = values.private_key;
        } else {
          formData.value = values.id;
        }
        onSuccess(formData);
        handleCancel();
      });
    };

    const handleCancel = () => {
      setGroupVisible(false);
      setAuthTypeValue(undefined);
      setUploadedFileName(undefined);
    };

    return (
      <div>
        <OperateModal
          width={400}
          title={title}
          visible={groupVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Form ref={formRef} name="basic" layout="vertical">
            <Form.Item name="private_key" hidden>
              <Input />
            </Form.Item>
            <Form.Item<ControllerInstallFields>
              label={t(
                `node-manager.cloudregion.node.${BATCH_FIELD_MAPS[field]}`
              )}
              name="id"
              rules={[
                {
                  required: true,
                  message: t('common.required'),
                  validator: (_, value) => {
                    if (
                      field === 'password' &&
                      authTypeValue === 'private_key'
                    ) {
                      return uploadedFileName
                        ? Promise.resolve()
                        : Promise.reject(new Error(t('common.required')));
                    }
                    return value
                      ? Promise.resolve()
                      : Promise.reject(new Error(t('common.required')));
                  },
                },
              ]}
            >
              {renderFormItem()}
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);
BatchEditModal.displayName = 'BatchEditModal';
export default BatchEditModal;
