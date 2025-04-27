'use client';

import React from 'react';
import EntityList from '@/app/opspilot/components/entity-list';
import GenericModifyModal from '@/app/opspilot/components/generic-modify-modal';
import StudioCard from '@/app/opspilot/components/studio/studioCard';
import { Studio } from '@/app/opspilot/types/studio';
import { message, Modal } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useStudioApi } from '@/app/opspilot/api/studio';

const StudioPage: React.FC = () => {
  const { t } = useTranslation();
  const { deleteStudio } = useStudioApi();

  const beforeDelete = (studio: Studio, deleteCallback: () => void) => {
    const onDelete = async () => {
      try {
        await deleteStudio(studio.id);
        deleteCallback();
        message.success(t('common.delSuccess'));
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

  return (
    <EntityList<Studio>
      endpoint="/opspilot/bot_mgmt/bot/"
      CardComponent={StudioCard}
      ModifyModalComponent={(props) => (
        <GenericModifyModal
          {...props}
          formType="studio"
        />
      )}
      itemTypeSingle="studio"
      beforeDelete={beforeDelete}
    />
  );
};

export default StudioPage;
