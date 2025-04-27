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

    useImperativeHandle(ref, () => ({
      showModal: ({ form, title, type }) => {
        // 开启弹窗的交互
        const formData = cloneDeep(form || {});
        setGroupForm(formData);
        setGroupVisible(true);
        setField(type || 'os');
        setTitle(title || '');
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
    }, [field]);

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        const formData: TableDataItem = {};
        formData.value = values.id;
        formData.field = field;
        onSuccess(formData);
        handleCancel();
      });
    };

    const handleCancel = () => {
      setGroupVisible(false);
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
            <Form.Item<ControllerInstallFields>
              label={t(
                `node-manager.cloudregion.node.${BATCH_FIELD_MAPS[field]}`
              )}
              name="id"
              rules={[{ required: true, message: t('common.required') }]}
            >
              {renderFormItem()}
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);
BatchEditModal.displayName = 'batchEditModal';
export default BatchEditModal;
