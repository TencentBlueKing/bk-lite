import React, { useState, useMemo, useCallback } from 'react';
import { Input, Spin, Dropdown, Tag, Button, Empty, Select, Space } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import styles from './index.module.scss';
import { EntityListProps } from '@/types';
import PermissionWrapper from '@/components/permission';

const { Search } = Input;

const EntityList = <T,>({
  data,
  loading,
  singleActionType = 'icon',
  searchSize = 'middle',
  filterOptions = [],
  filter = false,
  filterLoading = false,
  search = true,
  operateSection,
  menuActions,
  singleAction,
  openModal,
  onSearch,
  onCardClick,
  changeFilter,
  infoText,
}: EntityListProps<T>) => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState('');
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    if (onSearch) {
      onSearch(value);
    }
  };

  const handleFilter = (value: string[]) => {
    if (changeFilter) {
      changeFilter(value);
    }
  };

  const filteredItems = useMemo(() => {
    return data.filter((item) => (item as any).name?.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [data, searchTerm]);

  const renderCard = useCallback((item: T) => {
    const { id, name, description, icon, tagList } = item as any;
    const singleButtonAction = singleAction ? singleAction(item) : null;
    const isSingleButtonAction = singleButtonAction && singleActionType === 'button';
    const isSingleIconAction = singleActionType === 'icon' && singleButtonAction;

    return (
      <div
        key={id}
        className={`p-4 rounded-xl relative shadow-md ${onCardClick ? 'cursor-pointer' : ''} ${styles.commonCard}`}
        onClick={() => (onCardClick ? onCardClick(item) : undefined)}
        onMouseEnter={() => setHoveredCard((current) => (current !== id ? id : current))}
        onMouseLeave={() => setHoveredCard((current) => (current === id ? null : current))}
      >
        {menuActions && (
          <div className="absolute right-2 z-10 top-6" onClick={(e) => e.stopPropagation()}>
            <Dropdown overlay={menuActions(item) as React.ReactElement} trigger={['click']} placement="bottomRight">
              <div className="cursor-pointer">
                <Icon type="sangedian-copy" className="text-xl" />
              </div>
            </Dropdown>
          </div>
        )}
        {
          isSingleIconAction && (
            <div className="absolute right-4 z-10 top-6" onClick={(e) => {
              e.stopPropagation();
              singleButtonAction.onClick(item);
            }}>
              <Icon type="shezhi" className="text-base cursor-pointer" />
            </div>
          )
        }
        <div className="flex items-center">
          <div className="rounded-full">
            <Icon type={icon} className="text-4xl" />
          </div>
          <div className="ml-2">
            <h3 className="font-semibold truncate text-sm" title={name}>
              {name}
            </h3>
          </div>
        </div>
        <div className="h-[50px]">
          <p
            className={`text-xs mt-3 text-sm max-h-[66px] ${(isSingleButtonAction && hoveredCard === id) ? 'line-clamp-2' : 'line-clamp-3'} ${styles.desc}`}>{description}</p>
        </div>
        {(tagList && tagList.length > 0) || infoText ? (
          <div className="mt-2 flex justify-between items-end">
            <div>
              {tagList && tagList.length > 0 && tagList.map((t: any, idx: number) => (
                <Tag key={idx} className="mr-1 font-mini">
                  {t}
                </Tag>
              ))}
            </div>
            {infoText && <span className='text-[var(--color-text-4)] font-mini'>{infoText}</span>}
          </div>
        ) : null}
        {isSingleButtonAction && (
          <Button
            size="small"
            type="primary"
            className={`w-[92%] absolute bottom-2 left-1/2 transform -translate-x-1/2 ${hoveredCard === id ? '' : 'hidden'}`}
            onClick={(e) => {
              e.stopPropagation();
              singleButtonAction.onClick(item);
            }}
          >
            {singleButtonAction.text}
          </Button>
        )}
      </div>
    );
  }, [hoveredCard]);

  return (
    <div className="w-full h-full">
      <div className="flex justify-end mb-4">
        <Space.Compact>
          {filter && (<Select
            size={searchSize}
            allowClear={true}
            placeholder={`${t('common.select')}...`}
            mode="multiple"
            maxTagCount="responsive"
            className="w-[170px]"
            options={filterOptions}
            disabled={filterLoading}
            loading={filterLoading}
            onChange={handleFilter}
          />)}
          {search && (<Search
            size={searchSize}
            allowClear
            enterButton
            placeholder={`${t('common.search')}...`}
            className="w-60"
            onSearch={handleSearch}
          />)}
        </Space.Compact>
        {operateSection && <>{operateSection}</>}
      </div>
      {loading ? (
        <div className="min-h-[300px] flex items-center justify-center">
          <Spin spinning={loading}></Spin>
        </div>
      ) : (
        <>
          {filteredItems.length === 0 ? (
            <Empty description={t('common.noData')} />
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-6">
              {openModal && (
                <PermissionWrapper
                  requiredPermissions={['Add']}
                  className="shadow-md p-4 rounded-xl flex items-center justify-center cursor-pointer bg-[var(--color-bg)]"
                >
                  <div
                    className="w-full h-full flex items-center justify-center"
                    onClick={() => openModal()}
                  >
                    <div className="text-center">
                      <div className="text-2xl">+</div>
                      <div className="mt-2">{t('common.addNew')}</div>
                    </div>
                  </div>
                </PermissionWrapper>
              )}
              {filteredItems.map((item) => renderCard(item))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default EntityList;
