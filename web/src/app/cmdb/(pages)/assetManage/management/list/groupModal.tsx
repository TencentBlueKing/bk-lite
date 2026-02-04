'use client';

import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Input, Button, Form, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { GroupConfig, GroupFieldType } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { useClassificationApi } from '@/app/cmdb/api';

interface GroupModalProps {
  onSuccess: () => void;
}

export interface GroupModalRef {
  showModal: (info: GroupConfig) => void;
}

const GroupMoadal = forwardRef<GroupModalRef, GroupModalProps>(
  ({ onSuccess }, ref) => {
    const { createClassification, updateClassification } =
      useClassificationApi();
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const [groupVisible, setGroupVisible] = useState<boolean>(false);
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [groupForm, setGroupForm] = useState<GroupFieldType>({});
    const [subTitle, setSubTitle] = useState<string>('');
    const [title, setTitle] = useState<string>('');
    const [type, setType] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: ({ type, groupInfo, subTitle, title }) => {
        // 开启弹窗的交互
        setGroupVisible(true);
        setSubTitle(subTitle);
        setType(type);
        setTitle(title);
        setGroupForm(groupInfo);
      },
    }));

    useEffect(() => {
      if (groupVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(groupForm);
      }
    }, [groupVisible, groupForm]);

    const operateGroup = async (params: GroupFieldType) => {
      try {
        setConfirmLoading(true);
        const msg: string = t(
          type === 'add' ? 'successfullyAdded' : 'successfullyModified'
        );

        if (type === 'add') {
          await createClassification(params);
        } else {
          await updateClassification(groupForm.classification_id!, params);
        }

        message.success(msg);
        handleCancel();
        onSuccess();
      } catch (error) {
        console.error(error);
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleSubmit = () => {
      formRef.current?.validateFields().then((values) => {
        operateGroup(values);
      });
    };

    const handleCancel = () => {
      setGroupVisible(false);
    };

    return (
      <div>
        <OperateModal
          title={title}
          subTitle={subTitle}
          visible={groupVisible}
          onCancel={handleCancel}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={confirmLoading}
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <Form
            ref={formRef}
            name="basic"
            labelCol={{ span: 4 }}
            wrapperCol={{ span: 20 }}
          >
            <Form.Item<GroupFieldType>
              label="ID"
              name="classification_id"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input
                disabled={type === 'edit'}
                placeholder={t('common.inputTip')}
              />
            </Form.Item>
            <Form.Item<GroupFieldType>
              label="Name"
              name="classification_name"
              rules={[{ required: true, message: t('required') }]}
            >
              <Input placeholder={t('common.inputTip')} />
            </Form.Item>
          </Form>
        </OperateModal>
      </div>
    );
  }
);
GroupMoadal.displayName = 'GroupMoadal';
export default GroupMoadal;
