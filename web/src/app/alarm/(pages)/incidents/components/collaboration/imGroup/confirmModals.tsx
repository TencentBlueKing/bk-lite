'use client';

import { Input, Modal, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface PauseIMGroupModalProps {
  open: boolean;
  loading: boolean;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export const PauseIMGroupModal = ({
  open,
  loading,
  onConfirm,
  onCancel,
}: PauseIMGroupModalProps) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={t('incidents.imGroup.pauseConfirmTitle')}
      open={open}
      confirmLoading={loading}
      maskClosable={!loading}
      closable={!loading}
      okText={t('incidents.imGroup.pause')}
      cancelText={t('common.cancel')}
      onOk={() => void onConfirm()}
      onCancel={onCancel}
    >
      {t('incidents.imGroup.pauseConfirm')}
    </Modal>
  );
};

interface ContinuousSyncModalProps {
  open: boolean;
  enabled: boolean;
  loading: boolean;
  onChange: (enabled: boolean) => void;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export const ContinuousSyncModal = ({
  open,
  enabled,
  loading,
  onChange,
  onConfirm,
  onCancel,
}: ContinuousSyncModalProps) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={t('incidents.imGroup.continuousSync')}
      open={open}
      confirmLoading={loading}
      maskClosable={!loading}
      closable={!loading}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
      onOk={() => void onConfirm()}
      onCancel={onCancel}
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <span>{t('incidents.imGroup.continuousSync')}</span>
        <Switch checked={enabled} onChange={onChange} />
      </div>
      <div className="text-sm text-[var(--color-text-3)]">
        {enabled
          ? t('incidents.imGroup.continuousEnableConfirm')
          : t('incidents.imGroup.continuousDisableConfirm')}
      </div>
    </Modal>
  );
};

interface UnlinkIMGroupModalProps {
  open: boolean;
  groupName: string;
  confirmation: string;
  loading: boolean;
  onConfirmationChange: (value: string) => void;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}

export const UnlinkIMGroupModal = ({
  open,
  groupName,
  confirmation,
  loading,
  onConfirmationChange,
  onConfirm,
  onCancel,
}: UnlinkIMGroupModalProps) => {
  const { t } = useTranslation();
  return (
    <Modal
      title={t('incidents.imGroup.unlinkConfirm')}
      open={open}
      confirmLoading={loading}
      maskClosable={!loading}
      closable={!loading}
      okText={t('incidents.imGroup.unlink')}
      okButtonProps={{ danger: true, disabled: confirmation !== groupName }}
      cancelText={t('common.cancel')}
      onOk={() => void onConfirm()}
      onCancel={onCancel}
    >
      <p>{t('incidents.imGroup.unlinkImpact')}</p>
      <div className="text-sm font-medium mb-1">{t('incidents.imGroup.unlinkInputLabel')}</div>
      <Input
        value={confirmation}
        onChange={event => onConfirmationChange(event.target.value)}
        placeholder={groupName}
      />
    </Modal>
  );
};
