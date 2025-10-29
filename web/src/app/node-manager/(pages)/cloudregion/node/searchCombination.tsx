'use client';
import React, { useState, useEffect, useCallback } from 'react';
import { Select, Input } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { OPERATE_SYSTEMS } from '@/app/node-manager/constants/cloudregion';
import { useFieldOptions } from '@/app/node-manager/hooks/node';
import { SearchCombinationProps } from '@/app/node-manager/types/node';
const { Option } = Select;
const { Search } = Input;

const SearchCombination: React.FC<SearchCombinationProps> = ({
  defaultValue,
  className = '',
  onChange,
}) => {
  const { t } = useTranslation();
  const fieldOptions = useFieldOptions();
  const [selectedField, setSelectedField] = useState<string>('name');
  const [inputValue, setInputValue] = useState<string>('');
  const [selectValue, setSelectValue] = useState<string | undefined>(undefined);

  useEffect(() => {
    if (defaultValue) {
      setSelectedField(defaultValue.field);
      if (defaultValue.field === 'operating_system') {
        setSelectValue(defaultValue.value);
        setInputValue('');
      } else {
        setInputValue(defaultValue.value);
        setSelectValue(undefined);
      }
    }
  }, [defaultValue]);

  const handleFieldChange = useCallback((value: string) => {
    setSelectedField(value);
    setInputValue('');
    setSelectValue(undefined);
  }, []);

  const handleInputSearch = useCallback(
    (value: string) => {
      if (onChange) {
        onChange({
          field: selectedField,
          value: value.trim(),
        });
      }
    },
    [selectedField, onChange]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setInputValue(e.target.value);
    },
    []
  );

  const handleSelectChange = useCallback(
    (value: any) => {
      setSelectValue(value);
      if (onChange) {
        onChange({
          field: selectedField,
          value: value || '',
        });
      }
    },
    [selectedField, onChange]
  );

  const handleInputPressEnter = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        handleInputSearch(inputValue);
      }
    },
    [inputValue, handleInputSearch]
  );

  const renderRightComponent = () => {
    if (selectedField === 'operating_system') {
      return (
        <Select
          style={{ width: 200 }}
          placeholder={t('common.select')}
          value={selectValue}
          onChange={handleSelectChange}
          allowClear
          className="search-combination-right"
        >
          {OPERATE_SYSTEMS.map((option) => (
            <Option key={option.value} value={option.value}>
              {option.label}
            </Option>
          ))}
        </Select>
      );
    }

    return (
      <Search
        style={{ width: 200 }}
        placeholder={t('common.search')}
        value={inputValue}
        onChange={handleInputChange}
        onSearch={handleInputSearch}
        onPressEnter={handleInputPressEnter}
        enterButton={<SearchOutlined />}
        allowClear
        className="search-combination-right"
      />
    );
  };

  return (
    <>
      <style>
        {`
          .search-combination-wrapper .search-combination-left .ant-select-selector {
            border-top-right-radius: 0 !important;
            border-bottom-right-radius: 0 !important;
          }
          
          
          .search-combination-wrapper .search-combination-right .ant-select-selector {
            border-top-left-radius: 0 !important;
            border-bottom-left-radius: 0 !important;
          }
          
          .search-combination-wrapper .search-combination-right .ant-input-affix-wrapper {
            border-top-left-radius: 0 !important;
            border-bottom-left-radius: 0 !important;
          }
        `}
      </style>
      <div className={`search-combination-wrapper ${className}`}>
        <Select
          style={{ width: 120 }}
          value={selectedField}
          onChange={handleFieldChange}
          className="search-combination-left"
        >
          {fieldOptions.map((option) => (
            <Option key={option.value} value={option.value}>
              {option.label}
            </Option>
          ))}
        </Select>
        {renderRightComponent()}
      </div>
    </>
  );
};

export default SearchCombination;
