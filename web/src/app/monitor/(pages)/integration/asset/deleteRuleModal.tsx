'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Button, message } from 'antd';
import { ExclamationCircleFilled } from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import useIntegrationApi from '@/app/monitor/api/integration';
import { ModalRef } from '@/app/monitor/types';
import { useTranslation } from '@/utils/i18n';
import { cloneDeep } from 'lodash';

interface ModalProps {
  onSuccess: () => void;
}

const DeleteRuleModal = forwardRef<ModalRef, ModalProps>(
  ({ onSuccess }, ref) => {
    const { deleteInstanceGroupRule } = useIntegrationApi();
    const { t } = useTranslation();
    const [visible, setVisible] = useState<boolean>(false);
    const [deleteRuleLoading, setDeleteRuleLoading] = useState<boolean>(false);
    const [deleteGroupLoading, setDeleteGroupLoading] =
      useState<boolean>(false);
    const [configForm, setConfigForm] = useState<any>({});
    const [title, setTitle] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: ({ title, form }) => {
        setTitle(title);
        setConfigForm(cloneDeep(form));
        setVisible(true);
      },
    }));

    const handleOperate = async (type: boolean) => {
      const updateState = type ? setDeleteGroupLoading : setDeleteRuleLoading;
      updateState(true);
      try {
        await deleteInstanceGroupRule(configForm.id, {
          del_instance_org: type,
        });
        message.success(t('common.successfullyDeleted'));
        handleCancel();
        onSuccess();
      } finally {
        updateState(false);
      }
    };

    const handleCancel = () => {
      setVisible(false);
    };

    return (
      <div>
        <OperateModal
          width={430}
          closable={false}
          customHeaderClass=""
          title={
            <div className="flex w-full items-center p-[16px] pt-[20px]">
              <ExclamationCircleFilled className="mr-2 text-[22px] text-[var(--ant-color-warning)]" />
              <span>{title}</span>
            </div>
          }
          visible={visible}
          footer={
            <div>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={deleteRuleLoading}
                onClick={() => handleOperate(false)}
              >
                {t('monitor.integrations.deleteRules')}
              </Button>
              <Button
                className="mr-[10px]"
                type="primary"
                loading={deleteGroupLoading}
                onClick={() => handleOperate(true)}
              >
                {t('monitor.integrations.deleteGroup')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
          onCancel={handleCancel}
        >
          <div>{t('monitor.integrations.deleteRuleTips')}</div>
        </OperateModal>
      </div>
    );
  }
);
DeleteRuleModal.displayName = 'deleteRuleModal';
export default DeleteRuleModal;
