import React, { useEffect, useState } from 'react';
import { Spin, Tooltip, Button, Input, Empty } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import OperateModal from '@/components/operate-modal';
import { getIconTypeByIndex } from '@/app/opspilot/utils/knowledgeBaseUtils';
import { SelectorOption } from '@/app/opspilot/types/skill';

interface OperateModalProps {
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

const SelectorOperateModal: React.FC<OperateModalProps> = ({
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
  onCancel
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
        : [...prev, id]
    );
  };

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value.toLowerCase());
  };

  const handleOk = () => {
    onOk(tempSelectedOptions);
  };

  const handleConfigureOptions = () => {
    window.open('/opspilot/knowledge', '_blank');
  };

  const filteredOptions = options.filter((option) =>
    option.name?.toLowerCase().includes(searchTerm)
  );

  return (
    <OperateModal
      title={title || t('skill.selectKnowledgeBase')}
      visible={visible}
      okText={okText}
      cancelText={cancelText}
      onOk={handleOk}
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
          ) : (<Empty description={t('common.noData')}/>)
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
            <div className="grid grid-cols-3 gap-4 py-4 max-h-[50vh] overflow-y-auto">
              {filteredOptions.map((option, index) => {
                const tooltipContent = showToolDetail ? (
                  <div className="max-w-[280px]">
                    <div className="font-medium mb-1">{option.name}</div>
                    {option.description && (
                      <div className="text-xs text-gray-400 mb-2 line-clamp-3">{option.description}</div>
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
                ) : option.name;

                return (
                  <div
                    key={option.id}
                    className={`flex items-center p-4 border rounded-md cursor-pointer ${
                      tempSelectedOptions.includes(option.id) ? styles.selectedKnowledge : ''
                    }`}
                    onClick={() => handleOptionSelect(option.id)}
                  >
                    <div className="w-8 flex-shrink-0">
                      <Icon type={option.icon || getIconTypeByIndex(index)} className="text-2xl" />
                    </div>
                    <Tooltip title={tooltipContent} overlayInnerStyle={showToolDetail ? { padding: '12px' } : undefined}>
                      <span className="ml-2 inline-block max-w-[150px] whitespace-nowrap overflow-hidden text-ellipsis">
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
    </OperateModal>
  );
};

export default SelectorOperateModal;
