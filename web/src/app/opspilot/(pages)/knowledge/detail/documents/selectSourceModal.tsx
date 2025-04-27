import React, { useState, useEffect } from 'react';
import { Radio, Button } from 'antd';
import OperateModal from '@/components/operate-modal';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';

interface SelectSourceModalProps {
  defaultSelected: string;
  visible: boolean;
  onCancel: () => void;
  onConfirm: (selectedType: string) => void;
}

const SelectSourceModal: React.FC<SelectSourceModalProps> = ({ defaultSelected, visible, onCancel, onConfirm }) => {
  const [selectedType, setSelectedType] = useState<string>(defaultSelected);
  const { t } = useTranslation();

  useEffect(() => {
    setSelectedType(defaultSelected);
  }, [defaultSelected]);

  const radioOptions = [
    {
      value: 'file',
      title: t('knowledge.localFile'),
      subTitle: t('knowledge.fileSubTitle'),
    },
    {
      value: 'web_page',
      title: t('knowledge.webLink'),
      subTitle: t('knowledge.linkSubTitle'),
    },
    {
      value: 'manual',
      title: t('knowledge.cusText'),
      subTitle: t('knowledge.cusTextSubTitle'),
    },
  ];

  const handleConfirm = () => {
    onConfirm(selectedType);
  };

  return (
    <OperateModal
      title={`${t('common.select')}${t('knowledge.source')}`}
      visible={visible}
      onCancel={onCancel}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          {t('common.cancel')}
        </Button>,
        <Button key="confirm" type="primary" onClick={handleConfirm} disabled={!selectedType}>
          {t('common.confirm')}
        </Button>,
      ]}
    >
      <Radio.Group onChange={e => setSelectedType(e.target.value)} value={selectedType}>
        {radioOptions.map(option => (
          <Radio
            key={option.value}
            value={option.value}
            className={`${styles['radioItem']} ${selectedType === option.value ? styles['radioItemSelected'] : ''}`}
          >
            <div>
              <h3 className="text-sm">{option.title}</h3>
              <p className="mt-2 text-xs text-[var(--color-text-4)]">{option.subTitle}</p>
            </div>
          </Radio>
        ))}
      </Radio.Group>
    </OperateModal>
  );
};

export default SelectSourceModal;
