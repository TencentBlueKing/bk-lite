import React, { useState, useEffect, useMemo } from 'react';
import type { CheckboxProps, MenuProps } from 'antd';
import searchFilterStyle from './searchFilter.module.scss';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import GroupTreeSelector from '@/components/group-tree-select';
import { Select, Input, InputNumber, Checkbox, DatePicker, Button, Tag, Dropdown, Modal, message, Tooltip } from 'antd';
import { SearchOutlined, StarFilled, CloseOutlined, DownOutlined } from '@ant-design/icons';
import { UserItem } from '@/app/cmdb/types/assetManage';
import { useTranslation } from '@/utils/i18n';
import { SearchFilterProps } from '@/app/cmdb/types/assetData';
import { useAssetDataStore, type SavedFilter } from '@/app/cmdb/store';
import { useSavedFiltersApi, type SavedFiltersConfigValue } from '@/app/cmdb/api/userConfig';
import dayjs from 'dayjs';
import customParseFormat from 'dayjs/plugin/customParseFormat';

dayjs.extend(customParseFormat);

const SAVED_FILTERS_CONFIG_KEY = 'cmdb_saved_filters';

const SearchFilter: React.FC<SearchFilterProps> = ({
  attrList,
  userList,
  proxyOptions,
  showExactSearch = true,
  modelId = '',
  onSearch,
  onChange,
  onFilterChange,
}) => {
  const searchAttr_store = useAssetDataStore((state) => state.searchAttr);
  const userConfigs = useAssetDataStore((state) => state.user_configs);
  const updateUserConfig = useAssetDataStore((state) => state.updateUserConfig);
  const applySavedFilter = useAssetDataStore((state) => state.applySavedFilter);

  const { saveFilters } = useSavedFiltersApi();

  const savedFilters = useMemo(() => {
    const allFilters = userConfigs.cmdb_saved_filters as SavedFiltersConfigValue | undefined;
    return allFilters?.[modelId] || [];
  }, [userConfigs.cmdb_saved_filters, modelId]);

  const [searchAttr, setSearchAttr] = useState<string>("");
  const [searchValue, setSearchValue] = useState<any>('');
  const [isExactSearch, setIsExactSearch] = useState<boolean>(false);
  const { t } = useTranslation();
  const { RangePicker } = DatePicker;

  // 监听器，同步 store 中的 searchAttr 到本地状态
  useEffect(() => {
    if (searchAttr_store !== searchAttr) {
      setSearchAttr(searchAttr_store);
    }
  }, [searchAttr_store, searchAttr]);

  // 初始化默认字段
  useEffect(() => {
    if (attrList.length) {
      setSearchAttr(attrList[0].attr_id);
      useAssetDataStore.setState((state) => ({
        ...state,
        searchAttr: attrList[0].attr_id,
      }));
    }
  }, [attrList.length]);

  const onSearchValueChange = (value: any, isExact?: boolean) => {
    setSearchValue(value);
    const selectedAttr = attrList.find((attr) => attr.attr_id === searchAttr);
    let condition: any = {
      field: searchAttr,
      type: selectedAttr?.attr_type,
      value,
    };
    // 排除布尔类型的false || 多选框没选时的空数组
    if (
      (!value && value !== false && value !== 0) ||
      (Array.isArray(value) && !value.length) ||
      (selectedAttr?.attr_type === 'time' && !(value?.[0] && value?.[1]))
    ) {
      // condition 为 null 时，传递字段信息用于删除对应筛选项
      condition = { field: searchAttr } as any;
    } else if (selectedAttr?.attr_id === 'cloud') {
      condition.type = typeof value === 'number' ? 'int=' : 'str=';
    } else {
      switch (selectedAttr?.attr_type) {
        case 'enum':
          condition.type = typeof value === 'number' ? 'int=' : 'str=';
          break;
        case 'str':
          condition.type = isExact ? 'str=' : 'str*';
          break;
        case 'user':
          // test4.5:如果为用户字段user，则类型为list（operator 字段的数据类型转换）
          condition.type = 'list[]';
          condition.value = Array.isArray(value) ? value : [value];
          break;
        case 'int':
          condition.type = 'int=';
          condition.value = +condition.value;
          break;
        case 'organization':
          condition.type = 'list[]';
          break;
        case 'time':
          delete condition.value;
          condition.start = value.at(0);
          condition.end = value.at(-1);
          break;
      }
    }
    onSearch(condition, value);
  };

  const onSearchAttrChange = (attr: string) => {
    setSearchValue('');
    useAssetDataStore.setState((state) => ({
      ...state,
      searchAttr: attr,
    }));

    // 更新本地状态
    setSearchAttr(attr);
  };

  const onExactSearchChange: CheckboxProps['onChange'] = (e) => {
    const checked = e.target.checked;
    setIsExactSearch(checked);
    useAssetDataStore.setState((state) => ({
      ...state,
      case_sensitive: checked,
    }));
  };
  const handleSearchClick = () => {
    onSearchValueChange(searchValue, isExactSearch);
  };

  const handleApplySavedFilter = (filter: SavedFilter) => {
    const newFilters = applySavedFilter(filter);
    onChange?.(newFilters);
    onFilterChange?.(newFilters);
  };

  const handleDeleteSavedFilter = (filter: SavedFilter, e?: React.MouseEvent) => {
    e?.stopPropagation();
    
    Modal.confirm({
      title: t('common.confirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        try {
          const allSavedFilters = (userConfigs.cmdb_saved_filters ||
            {}) as SavedFiltersConfigValue;
          const currentFilters = allSavedFilters[modelId] || [];
          const updatedFilters = currentFilters.filter(
            (f) => f.id !== filter.id,
          );
          const updatedAllFilters: SavedFiltersConfigValue = {
            ...allSavedFilters,
            [modelId]: updatedFilters,
          };

          await saveFilters(SAVED_FILTERS_CONFIG_KEY, updatedAllFilters, false);
          updateUserConfig(SAVED_FILTERS_CONFIG_KEY, updatedAllFilters);

          message.success(t('FilterBar.deleteSuccess'));
        } catch {
          message.error(t('FilterBar.deleteFailed'));
        }
      },
    });
  };

  const visibleSavedFilters = savedFilters.slice(0, 3);
  const moreSavedFilters = savedFilters.slice(3);

  const moreFiltersMenuItems: MenuProps['items'] = moreSavedFilters.map((filter) => ({
    key: filter.id,
    label: (
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span onClick={() => handleApplySavedFilter(filter)}>{filter.name}</span>
        <CloseOutlined 
          style={{ marginLeft: 8, color: '#999', fontSize: '10px' }}
          onClick={(e) => handleDeleteSavedFilter(filter, e)} 
        />
      </div>
    ),
  }));

  const renderSearchInput = () => {
    const selectedAttr = attrList.find((attr) => attr.attr_id === searchAttr);
    // 特殊处理-主机的云区域为下拉选项
    if (selectedAttr?.attr_id === 'cloud' && proxyOptions.length) {
      return (
        <Select
          placeholder={t('common.selectTip')}
          allowClear
          showSearch
          className="value"
          style={{ width: 200 }}
          value={searchValue}
          onChange={(e) => onSearchValueChange(e, isExactSearch)}
          onClear={() => onSearchValueChange('', isExactSearch)}
        >
          {proxyOptions.map((opt) => (
            <Select.Option key={opt.proxy_id} value={opt.proxy_id}>
              {opt.proxy_name}
            </Select.Option>
          ))}
        </Select>
      );
    }
    switch (selectedAttr?.attr_type) {
      case 'user':
        return (
          // 筛选项搜索框中，用户字段为多选
          <Select
            mode="multiple"
            allowClear
            showSearch
            className="value"
            style={{ minWidth: 200 }}
            value={Array.isArray(searchValue) ? searchValue : searchValue ? [searchValue] : []}
            onChange={(e) => onSearchValueChange(e, isExactSearch)}
            onClear={() => onSearchValueChange('', isExactSearch)}
            maxTagCount={2}
            maxTagPlaceholder={(omittedValues) => `+${omittedValues.length}`}
            filterOption={(input, opt: any) => {
              if (typeof opt?.children?.props?.text === 'string') {
                return opt?.children?.props?.text
                  ?.toLowerCase()
                  .includes(input.toLowerCase());
              }
              return true;
            }}
          >
            {userList.map((opt: UserItem) => (
              <Select.Option key={opt.id} value={opt.id}>
                <EllipsisWithTooltip
                  text={`${opt.display_name}(${opt.username})`}
                  className="whitespace-nowrap overflow-hidden text-ellipsis break-all"
                />
              </Select.Option>
            ))}
          </Select>
        );
      case 'enum':
        return (
          <Select
            allowClear
            showSearch
            className="value"
            style={{ width: 200 }}
            value={searchValue}
            onChange={(e) => onSearchValueChange(e, isExactSearch)}
            onClear={() => onSearchValueChange('', isExactSearch)}
            filterOption={(input, opt: any) => {
              if (typeof opt?.children === 'string') {
                return opt?.children
                  ?.toLowerCase()
                  .includes(input.toLowerCase());
              }
              return true;
            }}
          >
            {selectedAttr.option?.map((opt) => (
              <Select.Option key={opt.id} value={opt.id}>
                {opt.name}
              </Select.Option>
            ))}
          </Select>
        );
      case 'bool':
        return (
          <Select
            allowClear
            className="value"
            style={{ width: 200 }}
            value={searchValue}
            onChange={(e) => onSearchValueChange(e, isExactSearch)}
            onClear={() => onSearchValueChange('', isExactSearch)}
          >
            {[
              { id: true, name: 'Yes' },
              { id: false, name: 'No' },
            ].map((opt) => (
              <Select.Option key={opt.id.toString()} value={opt.id}>
                {opt.name}
              </Select.Option>
            ))}
          </Select>
        );
      case 'organization':
        return (
          <GroupTreeSelector
            style={{ width: 200 }}
            value={searchValue}
            onChange={(e) => onSearchValueChange(e, isExactSearch)}
          />
        );
      case 'time':
        // 将字符串数组转换为 dayjs 对象数组，用于 RangePicker
        const getTimeValue = () => {
          if (!searchValue || !Array.isArray(searchValue)) {
            return [null, null];
          }
          // 如果已经是 dayjs 对象，直接使用
          if (searchValue[0] && typeof searchValue[0].isValid === 'function') {
            return [searchValue[0], searchValue[1] || null];
          }
          // 如果是字符串，转换为 dayjs 对象
          const start = searchValue[0] ? dayjs(searchValue[0], 'YYYY-MM-DD HH:mm', true) : null;
          const end = searchValue[1] ? dayjs(searchValue[1], 'YYYY-MM-DD HH:mm', true) : null;
          // 如果严格模式解析失败，尝试自动解析
          return [
            start && start.isValid() ? start : (searchValue[0] ? dayjs(searchValue[0]) : null),
            end && end.isValid() ? end : (searchValue[1] ? dayjs(searchValue[1]) : null),
          ];
        };
        return (
          <RangePicker
            allowClear
            style={{ width: 320 }}
            showTime={{ format: 'HH:mm' }}
            format="YYYY-MM-DD HH:mm"
            value={getTimeValue() as any}
            onChange={(value, dateString) => {
              onSearchValueChange(dateString, isExactSearch);
            }}
          />
        );
      case 'int':
        return (
          <InputNumber
            className="value"
            style={{ width: 200 }}
            value={searchValue}
            onChange={(val) => {
              setSearchValue(val);
              if (val === undefined || val === null) {
                onSearchValueChange('', isExactSearch);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                onSearchValueChange(searchValue, isExactSearch);
              }
            }}
          />
        );
      default:
        return (
          <Input
            allowClear
            className="value"
            style={{ width: 200 }}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            onClear={() => onSearchValueChange('', isExactSearch)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                onSearchValueChange(searchValue, isExactSearch);
              }
            }}
          />
        );
    }
  };

  return (
    <>
      <div className={searchFilterStyle.searchFilter + ' flex items-center'}>
        <Select
          className={searchFilterStyle.attrList}
          style={{ width: 120 }}
          value={searchAttr}
          onChange={onSearchAttrChange}
        >
          {attrList.map((attr) => (
            <Select.Option key={attr.attr_id} value={attr.attr_id}>
              {attr.attr_name}
            </Select.Option>
          ))}
        </Select>
        {renderSearchInput()}
        {/* 搜索按钮 */}
        <Button
          type="primary"
          icon={<SearchOutlined />}
          onClick={handleSearchClick}
          style={{
            marginLeft: 0,
            marginRight: 8,
            borderTopLeftRadius: 0,
            borderBottomLeftRadius: 0,
          }}
        ></Button>
        {showExactSearch && (
          <Checkbox onChange={onExactSearchChange}>
            {t('Model.isExactSearch')}
          </Checkbox>
        )}

        {/* 收藏的筛选条件 */}
        {savedFilters.length > 0 && (
          <div className={searchFilterStyle.savedFiltersWrapper}>
            <div className={searchFilterStyle.savedFiltersLabel}>
              <StarFilled className={searchFilterStyle.starIcon} />
              <span>{t('FilterBar.savedFilters')}：</span>
            </div>
            <div className={searchFilterStyle.savedFiltersTags}>
              {visibleSavedFilters.map((filter) => {
                const displayName =
                  filter.name.length > 6
                    ? `${filter.name.slice(0, 6)}...`
                    : filter.name;
                const tagContent = (
                  <Tag
                    key={filter.id}
                    className={searchFilterStyle.savedFilterTag}
                    onClick={() => handleApplySavedFilter(filter)}
                  >
                    <span>{displayName}</span>
                    <CloseOutlined
                      className={searchFilterStyle.closeIcon}
                      onClick={(e) => handleDeleteSavedFilter(filter, e)}
                    />
                  </Tag>
                );
                return filter.name.length > 6 ? (
                  <Tooltip key={filter.id} title={filter.name}>
                    {tagContent}
                  </Tooltip>
                ) : (
                  tagContent
                );
              })}
              {moreSavedFilters.length > 0 && (
                <Dropdown
                  menu={{ items: moreFiltersMenuItems }}
                  trigger={['click']}
                >
                  <Tag className={searchFilterStyle.moreFiltersTag}>
                    <span>{t('FilterBar.moreSavedFilters')}</span>
                    <DownOutlined className={searchFilterStyle.downIcon} />
                  </Tag>
                </Dropdown>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
};

export default SearchFilter;
