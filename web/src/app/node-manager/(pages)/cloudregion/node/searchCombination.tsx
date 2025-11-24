'use client';
import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Select, Button, Card, Checkbox } from 'antd';
import { useTranslation } from '@/utils/i18n';
import {
  SearchCombinationProps,
  FieldConfig,
  SearchFilters,
} from '@/app/node-manager/types/node';
const { Option } = Select;

const SearchCombination: React.FC<SearchCombinationProps> = ({
  className = '',
  onChange,
  fieldConfigs = [],
  fieldWidth = 120,
  selectWidth = 200,
}) => {
  const { t } = useTranslation();

  const [selectedField, setSelectedField] = useState<string>(
    fieldConfigs[0]?.name || ''
  );
  const [tags, setTags] = useState<string[]>([]);
  const [showEnumOptions, setShowEnumOptions] = useState(false);
  const [tempEnumValues, setTempEnumValues] = useState<string[]>([]);
  const [isFocused, setIsFocused] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const enumDropdownRef = useRef<HTMLDivElement>(null);
  const selectRef = useRef<any>(null);
  const isClearing = useRef(false);

  useEffect(() => {
    if (fieldConfigs && fieldConfigs.length > 0) {
      const initialTags: string[] = [];
      fieldConfigs.forEach((config) => {
        if (config.value) {
          if (config.lookup_expr === 'in' && Array.isArray(config.value)) {
            const displayNames = config.value
              .map(
                (id) => config.options?.find((opt) => opt.id === id)?.name || id
              )
              .join(', ');
            initialTags.push(`${config.label}: ${displayNames}`);
          } else if (typeof config.value === 'string' && config.value) {
            initialTags.push(`${config.label}: ${config.value}`);
          }
        }
      });
      setTags(initialTags);
    }
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(target) &&
        enumDropdownRef.current &&
        !enumDropdownRef.current.contains(target)
      ) {
        setIsFocused(false);
        setShowEnumOptions(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const getFieldConfigs = useCallback((): FieldConfig[] => {
    return fieldConfigs;
  }, [fieldConfigs]);

  const currentFieldConfig = getFieldConfigs().find(
    (config) => config.name === selectedField
  );
  const isEnumField = currentFieldConfig?.lookup_expr === 'in';

  const handleFieldChange = useCallback((value: string) => {
    setSelectedField(value);
    setShowEnumOptions(false);
    setTempEnumValues([]);
    setTimeout(() => {
      selectRef.current?.focus();
    }, 0);
  }, []);

  const handleTagsChange = useCallback(
    (newTags: string[]) => {
      const formattedTags = newTags.map((tag) => {
        if (tag.includes(': ')) {
          return tag;
        }
        const fieldLabel = currentFieldConfig?.label || selectedField;
        return `${fieldLabel}: ${tag}`;
      });
      const uniqueTags = Array.from(new Set(formattedTags));
      setTags(uniqueTags);

      // 如果是清空操作且是枚举字段,保持下拉框打开
      if (uniqueTags.length === 0 && isEnumField && isClearing.current) {
        isClearing.current = false;
        setTimeout(() => {
          setShowEnumOptions(true);
          setIsFocused(true);
          selectRef.current?.focus();
        }, 0);
      }

      const filters: SearchFilters = {};

      uniqueTags.forEach((tag) => {
        const [fieldPart, valuePart] = tag.split(': ');
        const fieldConfig = getFieldConfigs().find(
          (config) => config.label === fieldPart
        );

        if (!fieldConfig) return;

        const fieldName = fieldConfig.name;

        if (!filters[fieldName]) {
          filters[fieldName] = [];
        }

        if (fieldConfig.lookup_expr === 'in') {
          const displayNames = valuePart.split(', ');
          const ids = displayNames
            .map(
              (name: string) =>
                fieldConfig.options?.find(
                  (opt: { id: string; name: string }) => opt.name === name
                )?.id
            )
            .filter(Boolean) as string[];

          filters[fieldName].push({
            lookup_expr: 'in',
            value: ids,
          });
        } else {
          filters[fieldName].push({
            lookup_expr: fieldConfig.lookup_expr,
            value: valuePart,
          });
        }
      });

      onChange?.(filters);
    },
    [getFieldConfigs, selectedField, onChange, currentFieldConfig, isEnumField]
  );

  const handleEnumConfirm = useCallback(() => {
    if (tempEnumValues.length === 0) {
      setShowEnumOptions(false);
      setIsFocused(false);
      selectRef.current?.blur();
      return;
    }
    const fieldLabel = currentFieldConfig?.label || selectedField;
    const selectedOptions = tempEnumValues
      .map(
        (val: string) =>
          currentFieldConfig?.options?.find(
            (opt: { id: string; name: string }) => opt.id === val
          )?.name
      )
      .filter(Boolean)
      .join(', ');
    const newTag = `${fieldLabel}: ${selectedOptions}`;
    const newTags = [...tags, newTag];
    handleTagsChange(newTags);
    setTempEnumValues([]);
    setShowEnumOptions(false);
    setIsFocused(false);
    selectRef.current?.blur();
  }, [
    tempEnumValues,
    currentFieldConfig,
    selectedField,
    tags,
    handleTagsChange,
  ]);

  const handleEnumCancel = useCallback(() => {
    setTempEnumValues([]);
    setShowEnumOptions(false);
    setIsFocused(false);
    selectRef.current?.blur();
  }, []);

  const handleSelectFocus = useCallback(() => {
    setIsFocused(true);
    if (isEnumField) {
      setShowEnumOptions(true);
    }
  }, [isEnumField]);

  const handleSelectBlur = useCallback((e: React.FocusEvent) => {
    const relatedTarget = e.relatedTarget as Node;
    if (
      enumDropdownRef.current &&
      relatedTarget &&
      enumDropdownRef.current.contains(relatedTarget)
    ) {
      return;
    }
    if (!enumDropdownRef.current?.contains(document.activeElement)) {
      setIsFocused(false);
    }
  }, []);

  const handleCustomTagRender = useCallback((value: string) => {
    if (!value) {
      return '';
    }
    return value;
  }, []);

  const enumOptionsDropdown = (
    <Card
      size="small"
      bordered={false}
      style={{
        marginTop: 4,
      }}
      bodyStyle={{ padding: '8px' }}
      onMouseDown={(e) => {
        e.preventDefault();
      }}
    >
      <div style={{ marginBottom: 12, maxHeight: 400, overflow: 'auto' }}>
        {currentFieldConfig?.options?.map(
          (option: { id: string; name: string }) => (
            <div
              key={option.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: '4px 6px',
                cursor: 'pointer',
                borderRadius: '4px',
              }}
              className="enum-option-item"
              onClick={() => {
                if (tempEnumValues.includes(option.id)) {
                  setTempEnumValues(
                    tempEnumValues.filter((val) => val !== option.id)
                  );
                } else {
                  setTempEnumValues([...tempEnumValues, option.id]);
                }
              }}
            >
              <Checkbox
                checked={tempEnumValues.includes(option.id)}
                style={{ marginRight: '8px' }}
              />
              <span style={{ fontSize: '12px' }}>{option.name}</span>
            </div>
          )
        )}
      </div>

      <div
        style={{
          borderTop: '1px solid var(--color-border-1)',
          paddingTop: '8px',
          display: 'flex',
          justifyContent: 'flex-end',
          gap: '8px',
        }}
      >
        <Button
          size="small"
          onClick={handleEnumCancel}
          style={{ minWidth: '60px' }}
        >
          {t('common.cancel')}
        </Button>
        <Button
          type="primary"
          size="small"
          onClick={handleEnumConfirm}
          style={{ minWidth: '60px' }}
        >
          {t('common.confirm')}
        </Button>
      </div>
    </Card>
  );

  return (
    <>
      <style>
        {`
          .search-combination-base {
            position: relative;
            display: inline-block;
          }
          
          .search-combination-wrapper {
            position: fixed;
            z-index: 99;
          }
          
          .search-combination-controls {
            display: flex;
            height: 32px;
          }
          
          .search-combination-wrapper .search-combination-left .ant-select-selector {
            border-top-right-radius: 0 !important;
            border-bottom-right-radius: 0 !important;
          }
          
          .search-combination-right-wrapper {
            position: absolute;
            top: 0;
            z-index: 99;
          }
          
          .search-combination-wrapper .search-combination-right .ant-select-selector {
            border-top-left-radius: 0 !important;
            border-bottom-left-radius: 0 !important;
            max-height: 200px;
            overflow-y: auto;
          }
          
          .enum-options-dropdown {
            position: absolute;
            top: 100%;
            left: 0;
            z-index: 99;
            margin-top: 4px;
          }
          
          .enum-option-item:hover {
            background-color: var(--color-fill-2) !important;
          }

          .ant-card-body {
            position: fixed;
            background-color: var(--color-bg-1);
            min-width: 200px;
            box-shadow: rgba(0, 0, 0, 0.08) 0px 6px 16px 0px, rgba(0, 0, 0, 0.12) 0px 3px 6px -4px, rgba(0, 0, 0, 0.05) 0px 9px 28px 8px;
          }
        `}
      </style>
      <div
        className={`search-combination-base ${className}`}
        style={{
          width: fieldWidth + selectWidth,
          height: 32,
        }}
      >
        <div className="search-combination-wrapper" ref={wrapperRef}>
          <div className="search-combination-controls">
            <Select
              style={{ width: fieldWidth }}
              value={selectedField}
              onChange={handleFieldChange}
              className="search-combination-left"
              showSearch
              allowClear={false}
              optionFilterProp="children"
              filterOption={(input, option) =>
                (option?.children as any)
                  ?.toLowerCase()
                  .includes(input.toLowerCase())
              }
            >
              {getFieldConfigs().map((option) => (
                <Option key={option.name} value={option.name}>
                  {option.label}
                </Option>
              ))}
            </Select>

            <div
              className="search-combination-right-wrapper"
              style={{ left: fieldWidth }}
            >
              <Select
                ref={selectRef}
                mode="tags"
                allowClear
                style={{ width: selectWidth }}
                placeholder={
                  isEnumField ? t('common.select') : t('common.search')
                }
                value={tags}
                onChange={handleTagsChange}
                onFocus={handleSelectFocus}
                onBlur={handleSelectBlur}
                onClear={() => {
                  if (isEnumField) {
                    isClearing.current = true;
                  }
                }}
                onInputKeyDown={(e) => {
                  if (isEnumField) {
                    if (e.key !== 'Backspace' && e.key !== 'Delete') {
                      e.preventDefault();
                    }
                  }
                }}
                suffixIcon={null}
                open={false}
                tokenSeparators={isEnumField ? [] : [',']}
                className="search-combination-right"
                tagRender={({ value, onClose }) => {
                  if (!value) {
                    return <span style={{ display: 'none' }}></span>;
                  }
                  const currentIndex = tags.indexOf(value);
                  if (!isFocused && tags.length > 1) {
                    if (currentIndex === 0) {
                    } else if (currentIndex === 1) {
                      return (
                        <span
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            padding: '2px 8px',
                            background: 'var(--color-fill-2)',
                            borderRadius: '4px',
                            fontSize: '12px',
                            marginRight: '4px',
                            marginBottom: '2px',
                            color: 'var(--color-primary)',
                            fontWeight: 500,
                          }}
                        >
                          +{tags.length - 1}
                        </span>
                      );
                    } else {
                      return <span style={{ display: 'none' }}></span>;
                    }
                  }
                  return (
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        padding: '2px 8px',
                        marginBottom: '2px',
                        background: 'var(--color-fill-2)',
                        borderRadius: '4px',
                        fontSize: '12px',
                        marginRight: '4px',
                        maxWidth: '125px',
                      }}
                      title={handleCustomTagRender(value)}
                    >
                      <span
                        style={{
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          maxWidth: '150px',
                        }}
                      >
                        {handleCustomTagRender(value)}
                      </span>
                      <span
                        style={{
                          marginLeft: '4px',
                          cursor: 'pointer',
                          flexShrink: 0,
                        }}
                        onClick={onClose}
                      >
                        ×
                      </span>
                    </span>
                  );
                }}
              />
              {showEnumOptions && isEnumField && (
                <div className="enum-options-dropdown" ref={enumDropdownRef}>
                  {enumOptionsDropdown}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

export default SearchCombination;
