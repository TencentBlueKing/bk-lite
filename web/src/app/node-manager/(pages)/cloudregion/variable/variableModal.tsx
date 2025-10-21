'use client';
import React, {
  useState,
  useRef,
  forwardRef,
  useImperativeHandle,
  useEffect,
  useMemo,
} from 'react';
import { Input, Form, message, Select } from 'antd';
import OperateModal from '@/components/operate-modal';
import type { FormInstance } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ModalSuccess, ModalRef } from '@/app/node-manager/types';
import type { TableDataItem } from '@/app/node-manager/types';
import useApiCloudRegion from '@/app/node-manager/api/cloudRegion';
import useCloudId from '@/app/node-manager/hooks/useCloudRegionId';
import Password from '@/components/password';
import { ListItem } from '@/types';
const { Option } = Select;

const VariableModal = forwardRef<ModalRef, ModalSuccess>(
  ({ onSuccess }, ref) => {
    const { createVariable, updateVariable } = useApiCloudRegion();
    const cloudId = useCloudId();
    const { t } = useTranslation();
    const formRef = useRef<FormInstance>(null);
    const [variableVisible, setVariableVisible] = useState<boolean>(false);
    const [variableFormData, setVariableFormData] = useState<TableDataItem>();
    const [modalType, setModalType] = useState<string>('add');
    const [confirmLoading, setConfirmLoading] = useState<boolean>(false);
    const [dataTypeList, setDataTypeList] = useState<ListItem[]>([]);
    const [passwordResetted, setPasswordResetted] = useState<boolean>(false);

    const isAdd = useMemo(() => {
      return modalType === 'add';
    }, [modalType]);

    useImperativeHandle(ref, () => ({
      showModal: ({ type, form }) => {
        // 开启弹窗的交互
        setVariableVisible(true);
        setModalType(type);
        setVariableFormData({
          ...form,
          type: form?.type || 'str',
        });
        setDataTypeList([
          {
            id: 'str',
            name: t('node-manager.cloudregion.variable.string'),
          },
          {
            id: 'secret',
            name: t('node-manager.cloudregion.variable.password'),
          },
        ]);
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
      setPasswordResetted(false);
    };

    //添加变量
    const handleConfirm = async () => {
      formRef.current?.validateFields().then((values) => {
        operateVariable(values);
      });
    };

    const operateVariable = async (values: TableDataItem) => {
      setConfirmLoading(true);
      try {
        const { name, value, description, type: valueType } = values;
        const tempdata = {
          key: name,
          value,
          description,
          cloud_region_id: cloudId,
          type: valueType || 'str',
        };
        if (!passwordResetted && valueType === 'secret') {
          delete tempdata.value;
        }
        const request = isAdd
          ? createVariable(tempdata)
          : updateVariable(variableFormData?.key, tempdata);
        const msg = t(`common.${isAdd ? 'addSuccess' : 'updateSuccess'}`);
        await request;
        message.success(msg);
        onSuccess();
        handleCancel();
      } finally {
        setConfirmLoading(false);
      }
    };

    const handleReset = () => {
      setPasswordResetted(true);
    };

    return (
      <OperateModal
        title={t(`common.${modalType}`)}
        open={variableVisible}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={confirmLoading}
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
                message: t(
                  'node-manager.cloudregion.variable.variableNameTips'
                ),
              },
              {
                required: true,
                message: t('common.inputMsg'),
              },
            ]}
          >
            <Input placeholder={t('common.inputMsg')} />
          </Form.Item>
          <Form.Item
            name="type"
            label={t('node-manager.cloudregion.variable.valueType')}
            rules={[
              {
                required: true,
                message: t('common.selectMsg'),
              },
            ]}
          >
            <Select placeholder={t('common.selectMsg')} disabled={!isAdd}>
              {dataTypeList.map((item: ListItem) => (
                <Option value={item.id} key={item.id}>
                  {item.name}
                </Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prevValues, currentValues) =>
              prevValues.type !== currentValues.type
            }
          >
            {({ getFieldValue }) => {
              return (
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
                  {getFieldValue('type') === 'secret' ? (
                    <Password
                      placeholder={t('common.inputMsg')}
                      onReset={handleReset}
                    />
                  ) : (
                    <Input placeholder={t('common.inputMsg')} />
                  )}
                </Form.Item>
              );
            }}
          </Form.Item>
          <Form.Item
            name="description"
            label={t('node-manager.cloudregion.variable.desc')}
          >
            <Input.TextArea rows={5} placeholder={t('common.inputMsg')} />
          </Form.Item>
        </Form>
      </OperateModal>
    );
  }
);
VariableModal.displayName = 'variableModal';
export default VariableModal;
