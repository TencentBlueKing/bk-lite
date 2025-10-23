'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Button } from 'antd';
import Image from 'next/image';
import OperateModal from '@/components/operate-modal';
import { iconList } from '@/app/cmdb/utils/common';
import selectIconStyle from './selectIcon.module.scss';
import { useTranslation } from '@/utils/i18n';

interface SelectIconProps {
  onSelect: (type: string) => void;
}

interface ModelConfig {
  title: string;
  defaultIcon: string;
}

export interface SelectIconRef {
  showModal: (info: ModelConfig) => void;
}

const SelectIcon = forwardRef<SelectIconRef, SelectIconProps>(
  ({ onSelect }, ref) => {
    const { t } = useTranslation();
    const [visible, setVisible] = useState<boolean>(false);
    const [title, setTitle] = useState<string>('');
    const [activeIcon, setActiveIcon] = useState<string>('');

    useImperativeHandle(ref, () => ({
      showModal: ({ defaultIcon, title }) => {
        // 开启弹窗的交互
        setVisible(true);
        setTitle(title);
        setActiveIcon(defaultIcon);
      },
    }));

    const handleSubmit = () => {
      onSelect(activeIcon);
      handleCancel();
    };

    const handleCancel = () => {
      setVisible(false);
    };

    return (
      <div>
        <OperateModal
          title={title}
          visible={visible}
          onCancel={handleCancel}
          width={540}
          footer={
            <div>
              <Button
                type="primary"
                className="mr-[10px]"
                onClick={handleSubmit}
              >
                {t('common.confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('common.cancel')}</Button>
            </div>
          }
        >
          <ul
            style={{ maxHeight: '50vh' }}
            className={`flex flex-wrap overflow-y-auto ${selectIconStyle.selectIcon}`}
          >
            {iconList.map((item) => {
              return (
                <li
                  key={item.key + item.describe}
                  className={`${
                    selectIconStyle.modelIcon
                  } w-[80px] h-[70px] flex flex-col items-center justify-center p-1 ${
                    activeIcon === item.key ? selectIconStyle.active : ''
                  }`}
                  onClick={() => setActiveIcon(item.key)}
                >
                  <Image
                    src={`/app/assets/assetModelIcon/${item.url}.svg`}
                    className="block cursor-pointer mb-1"
                    alt={t('picture')}
                    width={34}
                    height={34}
                  />
                  <span className="text-[10px] text-center text-gray-600 leading-3 cursor-pointer max-w-full overflow-hidden text-ellipsis">
                    {item.describe}
                  </span>
                </li>
              );
            })}
          </ul>
        </OperateModal>
      </div>
    );
  }
);
SelectIcon.displayName = 'selectIcon';
export default SelectIcon;
