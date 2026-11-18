'use client';

import React from 'react';
import EntityList from '@/app/opspilot/components/entity-list';
import GenericModifyModal from '@/app/opspilot/components/generic-modify-modal';
import StudioCard from '@/app/opspilot/components/studio/studioCard';
import { Studio } from '@/app/opspilot/types/studio';
import { message, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useStudioApi } from '@/app/opspilot/api/studio';
import { notifyWebchatAppsChanged } from '@/app/(core)/components/global-webchat/apps-changed';
import { useUserInfoContext } from '@/context/userInfo';
import StudioRetirementNotice from './StudioRetirementNotice';

type StudioModifyModalProps = Omit<
  React.ComponentProps<typeof GenericModifyModal>,
  'formType'
>;

const StudioModifyModal: React.FC<StudioModifyModalProps> = (props) => (
  <GenericModifyModal
    {...props}
    formType="studio"
  />
);

const StudioPage: React.FC = () => {
  const { t } = useTranslation();
  const { userId } = useUserInfoContext();
  const { deleteStudio, toggleBotPin } = useStudioApi();

  const beforeDelete = (studio: Studio, deleteCallback: () => void) => {
    const onDelete = async () => {
      try {
        await deleteStudio(studio.id);
        deleteCallback();
        message.success(t('common.delSuccess'));
        notifyWebchatAppsChanged();
      } catch {
        message.error(t('common.delFailed'));
      }
    };

    if (studio.online) {
      Modal.confirm({
        title: t('studio.offDeleteConfirm'),
        okText: t('studio.offAndDel'),
        onOk: onDelete,
      });
    } else {
      Modal.confirm({
        title: t('studio.deleteConfirm'),
        onOk: onDelete,
      });
    }
  };

  const beforePin = async (studio: Studio) => {
    try {
      await toggleBotPin(studio.id);
      message.success(studio.is_pinned ? t('common.unpinSuccess') : t('common.pinSuccess'));
    } catch {
      message.error(t('common.operationFailed'));
    }
  };

  return (
    <>
      {userId && <StudioRetirementNotice key={userId} userId={userId} />}
      <EntityList<Studio>
        endpoint="/opspilot/bot_mgmt/bot/"
        CardComponent={StudioCard}
        ModifyModalComponent={StudioModifyModal}
        itemTypeSingle="studio"
        pageTitle={t('studio.pageTitle')}
        pageDescription={t('studio.pageDescription')}
        beforeDelete={beforeDelete}
        onTogglePin={beforePin}
      />
    </>
  );
};

export default StudioPage;
