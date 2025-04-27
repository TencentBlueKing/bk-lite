'use client';

import React, { useState, forwardRef, useImperativeHandle } from 'react';
import { Button, Tooltip } from 'antd';
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
          footer={
            <div>
              <Button
                type="primary"
                className="mr-[10px]"
                onClick={handleSubmit}
              >
                {t('confirm')}
              </Button>
              <Button onClick={handleCancel}>{t('cancel')}</Button>
            </div>
          }
        >
          <ul
            className={`flex flex-wrap overflow-y-auto ${selectIconStyle.selectIcon}`}
          >
            {iconList.map((item) => {
              return (
                <li
                  key={item.key + item.describe}
                  className={`${
                    selectIconStyle.modelIcon
                  } w-[50px] h-[50px] flex items-center justify-center ${
                    activeIcon === item.key ? selectIconStyle.active : ''
                  }`}
                  onClick={() => setActiveIcon(item.key)}
                >
                  <Tooltip placement="top" title={item.describe}>
                    <Image
                      src={`/app/assets/assetModelIcon/${item.url}.svg`}
                      className="block cursor-pointer"
                      alt={t('picture')}
                      width={25}
                      height={25}
                    />
                  </Tooltip>
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
