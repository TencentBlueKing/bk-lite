"use client";
import { ModalRef } from '@/app/monitor/types';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import { Button, Form, FormInstance, Input, Select, Switch } from 'antd';
import React, { useImperativeHandle, forwardRef, useRef, useEffect } from 'react';
import { useRasaFormManager } from '@/app/mlops/hooks/manage/useRasaForm';

interface RasaModalProps {
  selectKey: string;
  folder_id: string;
  onSuccess: () => void;
}

const RasaModal = forwardRef<ModalRef, RasaModalProps>(({ selectKey, folder_id, onSuccess }, ref) => {
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);

  const {
    visiable,
    confirmLoading,
    entityType,
    slotType,
    title,
    formData,
    showModal,
    handleSubmit,
    handleCancel,
    onEntityTypeChange,
    onSlotPredictionChange,
    onSlotTypeChange,
    handleKeyDown,
    handleNameChange,
    validateSampleList,
    renderElement,
    modalElement
  } = useRasaFormManager({
    selectKey,
    folder_id,
    formRef,
    onSuccess
  });

  useImperativeHandle(ref, () => ({
    showModal
  }));

  // 当模态框显示且有formData时，设置表单数据
  useEffect(() => {
    if (visiable && formRef.current && formData) {
      formRef.current?.resetFields();
      if (formData?.name) {
        formRef.current?.setFieldsValue({ name: formData?.name });
      }

      if (formData?.entity_type) {
        formRef.current?.setFieldsValue({ entity_type: formData?.entity_type });
        onEntityTypeChange(formData?.entity_type);
      } else if (formData?.slot_type) {
        onSlotTypeChange(formData?.slot_type);
        formRef.current?.setFieldsValue({
          slot_type: formData?.slot_type,
          is_apply: formData?.is_apply
        })
      }
    }
  }, [visiable]);

  return (
    <>
      <OperateModal
        title={t(`datasets.${title}`)}
        open={visiable}
        onCancel={handleCancel}
        footer={[
          <Button key='confirm' type='primary' loading={confirmLoading} onClick={handleSubmit}>
            {t(`common.confirm`)}
          </Button>,
          <Button key='cancel' type='default' onClick={handleCancel}>
            {t(`common.cancel`)}
          </Button>,
        ]}
      >
        <Form ref={formRef} layout='vertical'>
          <Form.Item
            name='name'
            label={t(`common.name`)}
            rules={[{ required: true, message: t('common.inputMsg') }]}
          >
            <Input
              placeholder={t(`common.inputMsg`)}
              onKeyDown={handleKeyDown}
              onChange={handleNameChange}
            />
          </Form.Item>
          {selectKey === 'entity' && (
            <>
              <Form.Item
                name='entity_type'
                label={t(`common.type`)}
                rules={[{ required: true, message: t('common.selectMsg') }]}
              >
                <Select
                  placeholder={t(`common.selectMsg`)}
                  options={[
                    { label: t(`datasets.entityText`), value: 'Text' },
                    { label: t(`datasets.entityLookup`), value: 'Lookup' }
                  ]}
                  onChange={onEntityTypeChange}
                />
              </Form.Item>
              {entityType === 'Lookup' && (
                <Form.Item
                  label={t(`datasets.example`)}
                  rules={[{ required: true, validator: validateSampleList }]}
                >
                  {renderElement}
                </Form.Item>
              )}
            </>
          )}
          {selectKey === 'slot' && (
            <>
              <Form.Item
                name="slot_type"
                label={t(`common.type`)}
                rules={[{ required: true, message: t(`common.selectMsg`) }]}
              >
                <Select options={[
                  {
                    label: 'text(记录普通文本)',
                    value: 'text'
                  },
                  {
                    label: 'categorical(记录分类类别，枚举)',
                    value: 'categorical'
                  },
                  {
                    label: 'float(记录数值类型)',
                    value: 'float'
                  },
                  {
                    label: 'list(保存多个值的列表)',
                    value: 'list'
                  },
                  {
                    label: 'bool(布尔值，是或者否)',
                    value: 'bool'
                  }
                ]} onChange={onSlotTypeChange} />
              </Form.Item>
              <Form.Item
                name={'is_apply'}
                label={t(`datasets.slotApply`)}
                rules={[{ required: true, message: t(`common.selectMsg`) }]}
              >
                <Switch onChange={onSlotPredictionChange} defaultChecked={false} />
              </Form.Item>
              {slotType === 'categorical' && (
                <>
                  <Form.Item
                    name='samplelist'
                    label={t(`datasets.category`)}
                    rules={[{ required: true, validator: validateSampleList }]}
                  >
                    {renderElement}
                  </Form.Item>
                </>
              )}
            </>
          )}
          {(!['entity', 'slot', 'story', 'action'].includes(selectKey)) && (
            <>
              <Form.Item
                label={selectKey === 'rule' ? t(`datasets.step`) : t(`datasets.example`)}
                rules={[{ required: true, validator: validateSampleList }]}
              >
                {renderElement}
              </Form.Item>
            </>
          )}
        </Form>
      </OperateModal>
      {modalElement}
    </>
  );
});

RasaModal.displayName = 'RasaModal';
export default RasaModal;