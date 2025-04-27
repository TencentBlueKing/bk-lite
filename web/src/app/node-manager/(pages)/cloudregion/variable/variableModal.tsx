'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
} from 'react';
import { Input, Form, message } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ModalSuccess, ModalRef } from '@/app/node-manager/types';
import type { TableDataItem } from '@/app/node-manager/types';
import useApiCloudRegion from '@/app/node-manager/api/cloudregion';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';

const VariableModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { createvariable, updatevariable } = useApiCloudRegion();
    const cloudId = useCloudId();
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    //设置弹窗状态
    const [variableVisible, setVariableVisible] = useState<boolean>(false);
    const [variableFormData, setVariableFormData] = useState<TableDataItem>();
    const [type, setType] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form }) => {
        // 开启弹窗的交互
        setVariableVisible(true);
        setType(type);
        setVariableFormData(form);
      },
    }));

    //初始化表单的数据
    useEffect(() => {
      if (variableVisible) {
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue(variableFormData);
      }
    }, [variableVisible, variableFormData]);

    //关闭用户的弹窗(取消和确定事件)
    const handleCancel = () => {
      setVariableVisible(false);
    };

    //添加变量
    const handleConfirm = async () => {
      formRef.current?.validateFields().then((values) => {
        const { name, value, description } = values;
        const tempdata = {
          key: name,
          value,
          description,
          cloud_region_id: cloudId,
        };
        //发起请求的类型（添加和编辑）
        if (type === 'add') {
          createvariable(tempdata).then(() => {
            message.success(t('common.addSuccess'));
            onSuccess();
          });
        } else {
          updatevariable(variableFormData?.key, tempdata).then(() => {
            message.success(t('common.updateSuccess'));
            onSuccess();
          });
        }
        setVariableVisible(false);
      });
    };

    return (
      <OperateModal
        title={type === 'add' ? t('common.add') : t('common.edit')}
        open={variableVisible}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        onCancel={handleCancel}
        onOk={handleConfirm}
      >
        <Form ref={formRef} layout="vertical" colon={false}>
          <Form.Item
            name="name"
            label={t('common.name')}
            rules={[
              {
                pattern: /^[A-Za-z0-9_]+$/,
                message: '仅允许字符 A-Z, a-z, 0-9, 和 _',
              },
              {
                required: true,
                message: t('common.inputMsg'),
              },
            ]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="value"
            label={t('node-manager.cloudregion.variable.value')}
            rules={[
              {
                required: true,
                message: t('common.inputMsg'),
              },
            ]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            name="description"
            label={t('node-manager.cloudregion.variable.desc')}
          >
            <Input.TextArea rows={5} />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);
VariableModal.displayName = 'variableModal';
export default VariableModal;
