"use client";
import OperateModal from '@/components/operate-modal';
import {
  Form,
  FormInstance,
  Button
} from 'antd';
import {
  useImperativeHandle,
  forwardRef,
  useRef
} from 'react';
import { ModalRef } from '@/app/mlops/types';
import { TrainTaskModalProps } from '@/app/mlops/types/task';
import { useTaskForm } from '@/app/mlops/hooks/task/useTrainTaskForm';
import { useTranslation } from '@/utils/i18n';

const TrainTaskModal = forwardRef<ModalRef, TrainTaskModalProps>(({ datasetOptions, activeTag, onSuccess }, ref) => {
  const { t } = useTranslation();
  const formRef = useRef<FormInstance>(null);
  const {
    modalState,
    // formRef,
    loadingState,
    showModal,
    handleSubmit,
    handleCancel,
    renderFormContent
  } = useTaskForm({ datasetOptions, activeTag, onSuccess, formRef }); // 使用统一入口

  useImperativeHandle(ref, () => ({
    showModal: ({ type, title, form }) => {
      showModal({ type, title: title as string, form });
    }
  }));

  return (
    <>
      <OperateModal
        title={t(`traintask.${modalState.title}`)}
        open={modalState.isOpen}
        onCancel={handleCancel}
        footer={[
          <Button key="submit" loading={loadingState.confirm} type="primary" onClick={handleSubmit}>
            {t('common.confirm')}
          </Button>,
          <Button key="cancel" onClick={handleCancel}>
            {t('common.cancel')}
          </Button>,
        ]}
      >
        <Form
          ref={formRef}
          layout="vertical"
        >
          {renderFormContent()}
        </Form>
      </OperateModal>
    </>
  );
});

TrainTaskModal.displayName = 'TrainTaskModal';
export default TrainTaskModal;