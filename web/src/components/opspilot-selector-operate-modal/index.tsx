'use client';

import React, { useEffect, useState } from 'react';
import { Spin, Tooltip, Button, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import CompactEmptyState from '@/components/compact-empty-state';
import Icon from '@/components/icon';
import OperateFormModal from '@/components/operate-form-modal';
import {
  getIconTypeByIndex,
  type SelectorOption,
} from '@/components/opspilot-selector-shared';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';

interface OpspilotSelectorOperateModalProps {
  visible: boolean;
  okText: string;
  title?: string;
  cancelText: string;
  options: SelectorOption[];
  selectedOptions: number[];
  loading?: boolean;
  isNeedGuide?: boolean;
  showToolDetail?: boolean;
  onOk: (selected: number[]) => void;
  onCancel: () => void;
}

const OpspilotSelectorOperateModal: React.FC<
  OpspilotSelectorOperateModalProps
> = ({
  visible,
  okText,
  title,
  cancelText,
  options,
  selectedOptions,
  loading = false,
  isNeedGuide = true,
  showToolDetail = false,
  onOk,
  onCancel,
}) => {
  const { t } = useTranslation();
  const [tempSelectedOptions, setTempSelectedOptions] = useState<number[]>([]);
  const [searchTerm, setSearchTerm] = useState<string>('');

  useEffect(() => {
    if (visible) {
      setTempSelectedOptions(selectedOptions);
    }
  }, [visible, selectedOptions]);

  const handleOptionSelect = (id: number) => {
    setTempSelectedOptions((prev) =>
      prev.includes(id)
        ? prev.filter((item) => item !== id)
        : [...prev, id],
    );
  };

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value.toLowerCase());
  };

  const handleConfigureOptions = () => {
    window.open('/opspilot/knowledge', '_blank');
  };

  const filteredOptions = options.filter((option) =>
    option.name?.toLowerCase().includes(searchTerm),
  );

  return (
    <OperateFormModal
      title={title || t('skill.selectKnowledgeBase')}
      visible={visible}
      confirmText={okText}
      cancelText={cancelText}
      onConfirm={() => onOk(tempSelectedOptions)}
      onCancel={onCancel}
      width={700}
    >
      <Spin spinning={loading}>
        {options.length === 0 ? (
          isNeedGuide ? (
            <div className="text-center">
              <p>{t('skill.settings.noKnowledgeBase')}</p>
              <Button type="link" onClick={handleConfigureOptions}>
                {t('skill.settings.clickHere')}
              </Button>
              {t('skill.settings.toConfigureKnowledgeBase')}
            </div>
          ) : (
            <CompactEmptyState
              description={t('common.noData')}
              className="py-6"
            />
          )
        ) : (
          <>
            <div className="flex justify-end">
              <Input
                className="w-[300px]"
                placeholder={`${t('common.search')}...`}
                suffix={<SearchOutlined />}
                onChange={handleSearch}
              />
            </div>
            <div className="grid max-h-[50vh] grid-cols-3 gap-4 overflow-y-auto py-4">
              {filteredOptions.map((option, index) => {
                const tooltipContent = showToolDetail ? (
                  <div className="max-w-[280px]">
                    <div className="mb-1 font-medium">{option.name}</div>
                    {option.description && (
                      <div className="mb-2 line-clamp-3 text-xs text-gray-400">
                        {option.description}
                      </div>
                    )}
                    <a
                      href={`/opspilot/tool?id=${option.id}&name=${encodeURIComponent(option.name || '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-400 hover:text-blue-300"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('common.viewDetails')}
                    </a>
                  </div>
                ) : (
                  option.name
                );

                return (
                  <div
                    key={option.id}
                    className={`flex cursor-pointer items-center rounded-md border p-4 ${
                      tempSelectedOptions.includes(option.id)
                        ? styles.selectedKnowledge
                        : ''
                    }`}
                    onClick={() => handleOptionSelect(option.id)}
                  >
                    <div className="w-8 flex-shrink-0">
                      <Icon
                        type={option.icon || getIconTypeByIndex(index)}
                        className="text-2xl"
                      />
                    </div>
                    <Tooltip
                      title={tooltipContent}
                      overlayInnerStyle={showToolDetail ? { padding: '12px' } : undefined}
                    >
                      <span className="ml-2 inline-block max-w-[150px] overflow-hidden text-ellipsis whitespace-nowrap">
                        {option.name}
                      </span>
                    </Tooltip>
                  </div>
                );
              })}
            </div>
            <div className="pt-4">
              {t('skill.selectedCount')}: {tempSelectedOptions.length}
            </div>
          </>
        )}
      </Spin>
    </OperateFormModal>
  );
};

export type { OpspilotSelectorOperateModalProps };
export default OpspilotSelectorOperateModal;
