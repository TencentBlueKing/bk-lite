'use client';

import React, { useEffect, useRef, useState } from 'react';
import searchFilterStyle from './index.module.scss';
import { Button, Input, Select, Spin } from 'antd';
import {
  SearchFilterProps,
  SearchFilterCondition,
} from '@/app/alarm/types/alarms';
import { useSourceApi } from '@/app/alarm/api/integration';
import { normalizeRuleTags } from '@/app/alarm/utils/multivalueRules';
import { useTranslation } from '@/utils/i18n';

const PUSH_SOURCE_MAX = 50;

const PushSourceSearchValue = ({
  value,
  onChange,
}: {
  value: string[];
  onChange: (value: string[]) => void;
}) => {
  const { t } = useTranslation();
  const { getPushSourceIdOptions } = useSourceApi();
  const [catalog, setCatalog] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const loaded = useRef(false);
  const pending = useRef(false);

  const load = async () => {
    if (pending.current || loaded.current) return;
    pending.current = true;
    setLoading(true);
    setFailed(false);
    try {
      const rows = await getPushSourceIdOptions();
      setCatalog(
        Array.isArray(rows)
          ? rows.filter((item): item is string => typeof item === 'string' && !!item.trim())
          : [],
      );
      loaded.current = true;
    } catch {
      setFailed(true);
    } finally {
      pending.current = false;
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const publish = (next: string[]) => onChange(normalizeRuleTags(next).slice(0, PUSH_SOURCE_MAX));

  return (
    <Select<string[]>
      allowClear
      showSearch
      mode="tags"
      className="value"
      style={{ width: 250 }}
      maxCount={PUSH_SOURCE_MAX}
      maxLength={256}
      maxTagCount={2}
      optionFilterProp="label"
      aria-label={t('alarmCommon.pushSourceSelect')}
      placeholder={t('alarmCommon.all')}
      value={value}
      loading={loading}
      options={catalog.map((item) => ({ value: item, label: item }))}
      onChange={(next) => publish(next)}
      notFoundContent={
        loading ? (
          <Spin size="small" />
        ) : failed ? (
          <Button type="link" onClick={() => void load()}>
            {t('alarmCommon.pushSourceOptionsRetry')}
          </Button>
        ) : (
          t('alarmCommon.pushSourceEmpty')
        )
      }
    />
  );
};

const SearchFilter: React.FC<SearchFilterProps> = ({ onSearch, attrList, condition }) => {
  const [searchAttr, setSearchAttr] = useState<string>('');
  const [searchValue, setSearchValue] = useState<any>('');

  useEffect(() => {
    if (condition?.field) {
      setSearchAttr(condition.field);
      setSearchValue(
        condition.value ?? (condition.type === 'push_source' ? [] : ''),
      );
      return;
    }
    if (attrList.length) {
      setSearchAttr(attrList[0].attr_id);
    }
  }, [attrList.length, condition]);

  const onSearchValueChange = (value: any) => {
    setSearchValue(value);
    const selectedAttr: any = attrList.find((attr) => attr.attr_id === searchAttr);
    const condition: SearchFilterCondition = {
      field: searchAttr,
      type: selectedAttr?.attr_type,
      value,
    };
    onSearch(condition, value);
  };

  const onSearchAttrChange = (attr: string) => {
    setSearchAttr(attr);
    const nextType = attrList.find((item) => item.attr_id === attr)?.attr_type;
    setSearchValue(nextType === 'push_source' ? [] : '');
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
            onChange={(e) => onSearchValueChange(e)}
            onClear={() => onSearchValueChange('')}
          >
            {selectedAttr.option?.map((opt: any) => (
              <Select.Option key={opt.id} value={opt.id}>
                {opt.name}
              </Select.Option>
            ))}
          </Select>
        );
      case 'push_source':
        return (
          <PushSourceSearchValue
            value={Array.isArray(searchValue) ? searchValue : []}
            onChange={onSearchValueChange}
          />
        );
      default:
        return (
          <Input
            allowClear
            className="value"
            style={{ width: 250 }}
            value={searchValue}
            onChange={(e) => setSearchValue(e.target.value)}
            onClear={() => onSearchValueChange('')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                onSearchValueChange(searchValue);
              }
            }}
          />
        );
    }
  };

  return (
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
    </div>
  );
};

export default SearchFilter;
