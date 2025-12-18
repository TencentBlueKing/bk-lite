'use client';
import React from 'react';
import { Button } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';

interface InstallCompleteProps {
  onReset: () => void;
  onFinish: () => void;
}

const InstallComplete: React.FC<InstallCompleteProps> = ({
  onReset,
  onFinish,
}) => {
  const { t } = useTranslation();

  const handleViewNodes = () => {
    onFinish();
  };

  const handleAddAnother = () => {
    onReset();
  };

  return (
    <div>
      <div className="text-center p-[20px]">
        <div className="mb-6">
          <div className="mx-auto flex items-center justify-center">
            <Icon type="yunhangzhongx" className="text-8xl" />
          </div>
        </div>
        <div className="mb-6">
          <div className="flex items-center justify-center mb-4">
            <Icon type="finish" className="text-4xl mr-2" />
            <h3 className="text-2xl font-bold text-gray-900">
              {t('node-manager.controller.installCompleteTitle')}
            </h3>
          </div>
          <p className="text-lg mb-3 leading-relaxed">
            {t('node-manager.controller.installCompleteDesc')}
          </p>
          <p className="text-base text-[var(--color-text-3)] leading-relaxed">
            {t('node-manager.controller.installCompleteSubDesc')}
          </p>
        </div>
        <div className="flex justify-center mb-[10px]">
          <Button type="primary" onClick={handleViewNodes}>
            {t('node-manager.controller.viewNodeList')}
          </Button>
          <Button onClick={handleAddAnother} className="ml-[10px]">
            {t('node-manager.controller.installAnother')}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default InstallComplete;
