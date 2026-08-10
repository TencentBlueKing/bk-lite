'use client';

import React, { useEffect, useState } from 'react';
import { Select, Input } from 'antd';
import searchFilterStyle from './index.module.scss';

export interface AlarmSearchFilterCondition {
  field: string;
  type: string;
  value: any;
}

export interface AlarmSearchFilterAttributeOption {
  id: string | number;
  name: string;
}

export interface AlarmSearchFilterAttribute {
  attr_id: string;
  attr_name: string;
  attr_type: string;
  is_required?: boolean;
  editable?: boolean;
  option?: AlarmSearchFilterAttributeOption[];
}

export interface AlarmSearchFilterProps {
  onSearch: (condition: AlarmSearchFilterCondition, rawValue?: any) => void;
  attrList: AlarmSearchFilterAttribute[];
}

const AlarmSearchFilter: React.FC<AlarmSearchFilterProps> = ({
  onSearch,
  attrList,
}) => {
  const [searchAttr, setSearchAttr] = useState<string>('');
  const [searchValue, setSearchValue] = useState<any>('');

  useEffect(() => {
    if (attrList.length) {
      setSearchAttr(attrList[0].attr_id);
    }
  }, [attrList]);

  const onSearchValueChange = (value: any) => {
    setSearchValue(value);
    const selectedAttr = attrList.find((attr) => attr.attr_id === searchAttr);
    const condition: AlarmSearchFilterCondition = {
      field: searchAttr,
      type: selectedAttr?.attr_type || '',
      value,
    };
    onSearch(condition, value);
  };

  const onSearchAttrChange = (attr: string) => {
    setSearchAttr(attr);
    setSearchValue('');
  };

  const renderSearchInput = () => {
    const selectedAttr = attrList.find((attr) => attr.attr_id === searchAttr);
    switch (selectedAttr?.attr_type) {
      case 'enum':
        return (
          <Select
            allowClear
            className="value"
            style={{ width: 250 }}
            value={searchValue}
            onChange={(value) => onSearchValueChange(value)}
            onClear={() => onSearchValueChange('')}
          >
            {selectedAttr.option?.map((opt) => (
              <Select.Option key={opt.id} value={opt.id}>
                {opt.name}
              </Select.Option>
            ))}
          </Select>
        );
      default:
        return (
          <Input
            allowClear
            className="value"
            style={{ width: 250 }}
            value={searchValue}
            onChange={(event) => setSearchValue(event.target.value)}
            onClear={() => onSearchValueChange('')}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                onSearchValueChange(searchValue);
              }
            }}
          />
        );
    }
  };

  return (
    <div className={`${searchFilterStyle.searchFilter} flex items-center`}>
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
    </div>
  );
};

export default AlarmSearchFilter;
