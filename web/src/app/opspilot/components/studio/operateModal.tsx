import React, { useState, useEffect } from 'react';
import { Spin, Button, Tooltip, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import styles from './index.module.scss';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import OperateModal from '@/components/operate-modal';

interface OperateModalProps {
  visible: boolean;
  okText: string;
  cancelText: string;
  onOk: (selectedItems: number[]) => void;
  onCancel: () => void;
  items: any[];
  selectedItems: number[];
  title: string;
  showEmptyPlaceholder?: boolean;
  iconTypes?: string[];
}

const StudioOperateModal: React.FC<OperateModalProps> = ({
  visible,
  okText,
  cancelText,
  onOk,
  onCancel,
  items,
  selectedItems,
  title,
  showEmptyPlaceholder = false,
}) => {
  const { t } = useTranslation();
  const [tempSelectedItem, setTempSelectedItem] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>('');

  useEffect(() => {
    setTempSelectedItem(selectedItems[0] ?? null);
  }, [selectedItems, visible]);

  const handleItemSelect = (id: number) => {
    setTempSelectedItem(id);
  };

  const renderFooter = () => {
    if (showEmptyPlaceholder) {
      return (
        <Button onClick={onCancel}>
          {cancelText}
        </Button>
      );
    }
    return undefined;
  };

  const handleConfirm = () => {
    if (tempSelectedItem !== null) {
      onOk([tempSelectedItem]);
    }
  };

  const handleModalCancel = () => {
    setTempSelectedItem(selectedItems[0] ?? null);
    onCancel();
  };

  const handleClickHere = () => {
    window.open('/skill', '_blank');
  };

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setSearchTerm(e.target.value);
  };

  const filteredItems = items.filter(item =>
    item.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <OperateModal
      title={title}
      visible={visible}
      okText={showEmptyPlaceholder ? undefined : okText}
      cancelText={cancelText}
      width={750}
      onOk={showEmptyPlaceholder ? undefined : handleConfirm}
      onCancel={handleModalCancel}
      footer={renderFooter()}
    >
      <Spin spinning={false}>
        {showEmptyPlaceholder ? (
          <div>
            {t('studio.settings.noSkillHasBeenSelected')}
            <a onClick={handleClickHere} style={{ color: 'var(--color-primary)', cursor: 'pointer' }}>
              {t('studio.settings.clickHere')}
            </a>
            {t('studio.settings.toConfigureSkills')}
          </div>
        ) : (
          <>
            <div className="flex justify-end">
              <Input className="w-[300px]" placeholder={`${t('common.search')}...`} suffix={<SearchOutlined />} onChange={handleSearch} />
            </div>
            <div className="grid grid-cols-3 gap-4 py-4 max-h-[60vh] overflow-y-auto">
              {filteredItems.map((item, index) => (
                <div
                  key={item.id}
                  className={`flex p-4 border rounded-md cursor-pointer ${styles.item} ${tempSelectedItem === item.id ? styles.selectedItem : ''}`}
                  onClick={() => handleItemSelect(item.id)}
                >
                  <Icon type={index % 2 ? 'theory' : 'jishuqianyan'} className="text-2xl mr-[8px]" />
                  <Tooltip title={item.name}>
                    <span className="overflow-hidden text-ellipsis whitespace-nowrap">{item.name}</span>
                  </Tooltip>
                </div>
              ))}
            </div>
            <div className="pt-4">
              {t('skill.selectedCount')}: {tempSelectedItem !== null ? 1 : 0}
            </div>
          </>
        )}
      </Spin>
    </OperateModal>
  );
};

export default StudioOperateModal;
