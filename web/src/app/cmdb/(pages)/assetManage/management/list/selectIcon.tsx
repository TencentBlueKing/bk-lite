'use client';

import React, {
  useMemo,
  useState,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { Button, Empty, Input } from 'antd';
import Image from 'next/image';
import OperateModal from '@/components/operate-modal';
import {
  getSelectedModelIconValue,
  iconList,
} from '@/app/cmdb/utils/modelIcon';
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
    const [selectedIcon, setSelectedIcon] = useState<string>('');
    const [searchText, setSearchText] = useState<string>('');
    const [keyword, setKeyword] = useState<string>('');

    const filteredIconList = useMemo(() => {
      const normalizedKeyword = keyword.trim().toLocaleLowerCase();
      if (!normalizedKeyword) return iconList;

      return iconList.filter((item) =>
        [item.describe, item.key, item.url].some((value) =>
          value?.toLocaleLowerCase().includes(normalizedKeyword)
        )
      );
    }, [keyword]);

    useImperativeHandle(ref, () => ({
      showModal: ({ defaultIcon, title }) => {
        // 开启弹窗的交互
        setVisible(true);
        setTitle(title);
        setActiveIcon(getSelectedModelIconValue(defaultIcon));
        setSelectedIcon(defaultIcon);
        setSearchText('');
        setKeyword('');
      },
    }));

    const handleSubmit = () => {
      onSelect(selectedIcon);
      handleCancel();
    };

    const handleCancel = () => {
      setVisible(false);
      setSearchText('');
      setKeyword('');
    };

    const handleSearch = (value: string) => {
      setKeyword(value);
    };

    const handleSearchClear = () => {
      setSearchText('');
      setKeyword('');
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
          <Input.Search
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            onSearch={handleSearch}
            onClear={handleSearchClear}
            placeholder={t('Model.searchIcon')}
            aria-label={t('Model.searchIcon')}
            allowClear
            className="mb-4"
          />
          <div
            style={{ height: 'min(420px, calc(100vh - 280px))' }}
            className="overflow-y-auto"
          >
            {filteredIconList.length > 0 ? (
              <ul
                className={`flex flex-wrap content-start ${selectIconStyle.selectIcon}`}
              >
                {filteredIconList.map((item) => {
                  return (
                    <li
                      key={item.value}
                      className={`${
                        selectIconStyle.modelIcon
                      } w-[80px] h-[70px] flex flex-col items-center justify-center p-1 ${
                        activeIcon === item.value ? selectIconStyle.active : ''
                      }`}
                      onClick={() => {
                        setActiveIcon(item.value);
                        setSelectedIcon(item.value);
                      }}
                    >
                      <Image
                        src={item.src}
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
            ) : (
              <div className="flex h-full items-center justify-center">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t('common.noResult')}
                />
              </div>
            )}
          </div>
        </OperateModal>
      </div>
    );
  }
);
SelectIcon.displayName = 'selectIcon';
export default SelectIcon;
