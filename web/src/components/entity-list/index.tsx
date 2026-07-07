import React, { useState, useMemo, useCallback } from 'react';
import { Input, Spin, Dropdown, Tag, Button, Empty, Select, Space, Tooltip } from 'antd';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import styles from './index.module.scss';
import { EntityListProps } from '@/types';
import PermissionWrapper from '@/components/permission';

const { Search } = Input;
const TAG_COLOR_MAP: Record<string, string> = {
  search: 'blue',
  搜索: 'blue',
  general: 'cyan',
  通用: 'cyan',
  maintenance: 'green',
  运维: 'green',
  media: 'magenta',
  媒体: 'magenta',
  collaboration: 'geekblue',
  协作: 'geekblue',
  other: 'gold',
  其他: 'gold',
};

const getTagColor = (value: unknown) => {
  const text = String(value || '').trim();
  return TAG_COLOR_MAP[text] || 'blue';
};

const EntityList = <T,>({
  data,
  loading,
  singleActionType = 'icon',
  searchSize = 'middle',
  filterOptions = [],
  filter = false,
  filterLoading = false,
  search = true,
  toolbarPrefix,
  operateSection,
  menuActions,
  singleAction,
  openModal,
  onSearch,
  onCardClick,
  changeFilter,
  infoText,
  nameField = 'name',
  iconRender,
  descSlot,
  showBuiltinTag = true,
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
    return data.filter((item) => (item as any)[nameField]?.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [data, searchTerm, nameField]);

  const renderAddButton = useCallback(() => {
    if (!openModal) return null;
    
    return (
      <PermissionWrapper
        requiredPermissions={['Add']}
        className="shadow-md p-4 rounded-xl flex items-center justify-center cursor-pointer bg-[var(--color-bg)]"
      >
        <div
          className={`w-full h-full flex items-center justify-center ${styles.addNew}`}
          onClick={(e) => {
            e.preventDefault();
            openModal();
          }}
        >
          <div className="text-center">
            <div className="text-2xl">+</div>
            <div className="mt-2">{t('common.addNew')}</div>
          </div>
        </div>
      </PermissionWrapper>
    );
  }, [openModal, t]);

  const renderCard = useCallback((item: T) => {
    const { id, description, icon, tagList, is_build_in } = item as any;
    const name = (item as any)[nameField];
    const singleButtonAction = singleAction ? singleAction(item) : null;
    const isSingleButtonAction = singleButtonAction && singleActionType === 'button';
    const isSingleIconAction = singleActionType === 'icon' && singleButtonAction;

    return (
      <div
        key={id}
        className={`p-4 rounded-xl relative shadow-md flex flex-col ${onCardClick ? 'cursor-pointer' : ''} ${styles.commonCard}`}
        onClick={() => (onCardClick ? onCardClick(item) : undefined)}
        onMouseEnter={() => setHoveredCard((current) => (current !== id ? id : current))}
        onMouseLeave={() => setHoveredCard((current) => (current === id ? null : current))}
      >
        {menuActions && (
          <div className="absolute right-2 z-1 top-6" onClick={(e) => e.stopPropagation()}>
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
        <div className={`relative flex items-center ${isSingleButtonAction ? 'pr-8' : ''}`}>
          <div className="rounded-full">
            {iconRender ? iconRender(icon) : <Icon type={icon} className="text-4xl" />}
          </div>
          <div className="ml-2 min-w-0">
            <h3 className="font-semibold truncate text-sm" title={name}>
              {name}
            </h3>
          </div>
          {isSingleButtonAction && hoveredCard === id && (
            <Tooltip title={singleButtonAction.text}>
              <Button
                type="text"
                size="small"
                className="absolute right-0 top-1/2 -translate-y-1/2"
                icon={<Icon type="bianji" className="text-base" />}
                onClick={(e) => {
                  e.stopPropagation();
                  singleButtonAction.onClick(item);
                }}
              />
            </Tooltip>
          )}
        </div>
        <div className="flex-1 min-h-[50px]">
          <p
            className={`text-xs mt-3 text-sm max-h-[66px] line-clamp-3 ${styles.desc}`}>{description}</p>
        </div>
        <div className="mt-auto pt-4 flex justify-between items-center">
          <div className="flex flex-wrap gap-1">
            {tagList && tagList.length > 0 && tagList.map((t: any, idx: number) => {
              if (typeof t === 'object' && t.name) {
                return (
                  <Tooltip key={idx} title={t.tooltip}>
                    <Tag color={t.color} className="mr-1 font-mini">
                      {t.name}
                    </Tag>
                  </Tooltip>
                );
              }
              return (
                <Tag key={idx} color={getTagColor(t)} className="mr-1 font-mini">
                  {t}
                </Tag>
              );
            })}
            {showBuiltinTag && is_build_in !== undefined && (
              <Tag color={is_build_in ? 'blue' : 'green'} className="mr-1 font-mini">
                {is_build_in ? t('common.builtin') : t('common.externalApp')}
              </Tag>
            )}
            {infoText && <span className='text-[var(--color-text-4)] font-mini'>{infoText}</span>}
          </div>
          {descSlot && descSlot(item)}
        </div>
      </div>
    );
  }, [descSlot, hoveredCard, iconRender, infoText, menuActions, nameField, onCardClick, showBuiltinTag, singleAction, singleActionType, t]);

  return (
    <div className="w-full h-full">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {toolbarPrefix}
        </div>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
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
      </div>
      {loading ? (
        <div className="min-h-[300px] flex items-center justify-center">
          <Spin spinning={loading}></Spin>
        </div>
      ) : (
        <div className="@container">
          {filteredItems.length === 0 ? (
            openModal ? (
              <div className="grid grid-cols-1 @sm:grid-cols-2 @md:grid-cols-3 @lg:grid-cols-4 @7xl:grid-cols-5 gap-6">
                {renderAddButton()}
              </div>
            ) : (
              <Empty description={t('common.noData')} />
            )
          ) : (
            <div className="grid grid-cols-1 @sm:grid-cols-2 @md:grid-cols-3 @lg:grid-cols-4 @7xl:grid-cols-5 gap-6">
              {openModal && renderAddButton()}
              {filteredItems.map((item) => renderCard(item))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default EntityList;
