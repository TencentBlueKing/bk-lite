'use client';

import React, { useState } from 'react';
import { Button, Checkbox, Modal, Typography } from 'antd';
import { WarningOutlined } from '@ant-design/icons';
import SecretValueDisplay from '@/components/secret-value-display';
import { useTranslation } from '@/utils/i18n';

interface OpenApiTokenRevealModalProps {
  open: boolean;
  secret: string;
  onClose: () => void;
}

const OpenApiTokenRevealModal: React.FC<OpenApiTokenRevealModalProps> = ({
  open,
  secret,
  onClose,
}) => {
  const { t } = useTranslation();
  const [saved, setSaved] = useState(false);

  const handleClose = () => {
    setSaved(false);
    onClose();
  };

  return (
    <Modal
      title={t('system.settings.secret.createSuccessTitle')}
      open={open}
      closable={false}
      maskClosable={false}
      destroyOnHidden
      afterOpenChange={(isOpen) => {
        if (!isOpen) {
          setSaved(false);
        }
      }}
      footer={
        <div className="flex items-center justify-between pt-2">
          <Checkbox
            key="checked"
            className="text-xs text-[var(--color-text-1)] select-none"
            checked={saved}
            onChange={(event) => setSaved(event.target.checked)}
          >
            {t('system.settings.secret.confirmSave')}
          </Checkbox>
          <Button
            key="confirm"
            type="primary"
            disabled={!saved}
            onClick={handleClose}
          >
            {t('system.settings.secret.savedAction')}
          </Button>
        </div>
      }
    >
      <div className="my-3 flex items-start gap-2.5 rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-2)] p-3.5 text-xs text-[var(--color-text-2)]">
        <WarningOutlined className="mt-0.5 shrink-0 text-sm text-[var(--color-warning)]" />
        <span className="leading-relaxed">
          {t('system.settings.secret.createSuccessDesc')}
        </span>
      </div>

      <div className="mb-1.5 flex items-center justify-between">
        <Typography.Text strong className="text-xs text-[var(--color-text-1)]">
          {t('system.settings.secret.key')}
        </Typography.Text>
      </div>

      <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)] p-3">
        <SecretValueDisplay
          value={secret}
          masked={false}
          className="w-full justify-between font-mono text-sm break-all"
        />
      </div>
    </Modal>
  );
};

export default OpenApiTokenRevealModal;
