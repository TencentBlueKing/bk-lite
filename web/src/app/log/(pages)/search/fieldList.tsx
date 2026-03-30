'use client';
import React, { useState, useMemo, useCallback } from 'react';
import {
  CloseOutlined,
  MoreOutlined,
  PlusOutlined,
  HolderOutlined,
  CaretRightFilled,
  CaretDownFilled
} from '@ant-design/icons';
import { Input, Empty, Button, Spin, Progress } from 'antd';
import VirtualList from 'rc-virtual-list';
import CustomPopover from './customPopover';
import { useTranslation } from '@/utils/i18n';
import searchStyle from './index.module.scss';
import { FieldListProps, FieldTopValue } from '@/app/log/types/search';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { cloneDeep } from 'lodash';
import useSearchApi from '@/app/log/api/search';

const DEFAULT_FIELDS = ['timestamp', 'message'];
const DEFAULT_FIELDS_MAP: Record<string, string> = {
  timestamp: '_time',
  message: '_msg'
};

// 不显示展开按钮的字段
const HIDDEN_EXPAND_FIELDS = ['timestamp'];

// 虚拟滚动配置
const ITEM_HEIGHT = 32;

const FieldList: React.FC<FieldListProps> = ({
  fields,
  className = '',
  style = {},
  addToQuery,
  changeDisplayColumns,
  getSearchParams
}) => {
  const { t } = useTranslation();
  const { getFieldTopStats } = useSearchApi();
  const [searchText, setSearchText] = useState<string>('');
  const [displayFields, setDisplayFields] = useState<string[]>(() => {
    const stored = localStorage.getItem('logSearchFields');
    if (stored) {
      const parsed = JSON.parse(stored);
      // 确保始终包含默认字段
      const result = [...parsed];
      DEFAULT_FIELDS.forEach((field) => {
        if (!result.includes(field)) {
          result.unshift(field);
        }
      });
      return result;
    }
    return DEFAULT_FIELDS;
  });

  // 拖拽状态
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  // 展开状态管理
  const [expandedFields, setExpandedFields] = useState<Set<string>>(new Set());
  const [loadingFields, setLoadingFields] = useState<Set<string>>(new Set());
  const [fieldTopValues, setFieldTopValues] = useState<
    Record<string, FieldTopValue[]>
  >({});

  const CONTAINER_HEIGHT =
    +(style.height || '').toString().replace('px', '') || 400;

  const hiddenFields = useMemo(() => {
    return fields.filter(
      (item) => ![...displayFields, '_msg', '_time', '*'].includes(item)
    );
  }, [fields, displayFields]);

  const filteredDisplayFields = useMemo(() => {
    if (!searchText) {
      return displayFields;
    }
    return displayFields.filter((item) =>
      item.toLowerCase().includes(searchText.toLowerCase())
    );
  }, [displayFields, searchText]);

  const filteredHiddenFields = useMemo(() => {
    if (!searchText) {
      return hiddenFields;
    }
    return hiddenFields.filter((item) =>
      item.toLowerCase().includes(searchText.toLowerCase())
    );
  }, [hiddenFields, searchText]);

  // 计算展示字段区域的高度（简化计算，用于可选字段容器高度）
  const displayFieldsHeight = useMemo(() => {
    // title + items + margin
    return ITEM_HEIGHT + filteredDisplayFields.length * ITEM_HEIGHT;
  }, [filteredDisplayFields]);

  // 可选字段容器高度
  const hiddenFieldsContainerHeight = useMemo(() => {
    const available = CONTAINER_HEIGHT - displayFieldsHeight - ITEM_HEIGHT;
    return Math.max(100, available);
  }, [CONTAINER_HEIGHT, displayFieldsHeight]);

  // 展开/收起字段
  const toggleFieldExpand = useCallback(
    async (field: string, e: React.MouseEvent) => {
      e.stopPropagation();

      const isExpanded = expandedFields.has(field);

      if (isExpanded) {
        // 收起
        setExpandedFields((prev) => {
          const newSet = new Set(prev);
          newSet.delete(field);
          return newSet;
        });
      } else {
        // 展开，每次都重新加载数据
        setExpandedFields((prev) => new Set(prev).add(field));

        // 加载Top5数据
        setLoadingFields((prev) => new Set(prev).add(field));

        try {
          const searchParams = getSearchParams?.();
          if (searchParams) {
            const data = await getFieldTopStats({
              query: searchParams.query || '*',
              start_time: searchParams.start_time,
              end_time: searchParams.end_time,
              attr: field,
              top_num: 5,
              log_groups: searchParams.log_groups || []
            });
            setFieldTopValues((prev) => ({
              ...prev,
              [field]: data?.items || []
            }));
          }
        } catch (error) {
          console.error('Failed to fetch field top values:', error);
          setFieldTopValues((prev) => ({
            ...prev,
            [field]: []
          }));
        } finally {
          setLoadingFields((prev) => {
            const newSet = new Set(prev);
            newSet.delete(field);
            return newSet;
          });
        }
      }
    },
    [expandedFields, getSearchParams, getFieldTopStats]
  );

  // 判断字段是否显示展开按钮
  const shouldShowExpandButton = useCallback((field: string) => {
    return !HIDDEN_EXPAND_FIELDS.includes(field);
  }, []);

  const operateFields = useCallback(
    (type: string, field: string) => {
      let storageFileds = cloneDeep(displayFields);
      if (type === 'add') {
        storageFileds = [...storageFileds, field];
      } else {
        const index = storageFileds.findIndex((item) => item === field);
        if (index !== -1) {
          storageFileds.splice(index, 1);
        }
      }
      setDisplayFields(storageFileds);
      localStorage.setItem('logSearchFields', JSON.stringify(storageFileds));
      changeDisplayColumns(storageFileds);
    },
    [displayFields, changeDisplayColumns]
  );

  // 原生拖拽事件处理
  const handleDragStart = useCallback(
    (e: React.DragEvent<HTMLLIElement>, index: number) => {
      setDraggedIndex(index);
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', index.toString());
      if (e.currentTarget) {
        e.currentTarget.style.opacity = '0.5';
      }
    },
    []
  );

  const handleDragEnd = useCallback((e: React.DragEvent<HTMLLIElement>) => {
    setDraggedIndex(null);
    if (e.currentTarget) {
      e.currentTarget.style.opacity = '1';
    }
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLLIElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLLIElement>, dropIndex: number) => {
      e.preventDefault();
      const dragIndex = parseInt(e.dataTransfer.getData('text/plain'), 10);

      if (dragIndex !== dropIndex && !isNaN(dragIndex)) {
        const newFields = [...displayFields];
        const [removed] = newFields.splice(dragIndex, 1);
        newFields.splice(dropIndex, 0, removed);

        setDisplayFields(newFields);
        localStorage.setItem('logSearchFields', JSON.stringify(newFields));
        changeDisplayColumns(newFields);
      }

      setDraggedIndex(null);
    },
    [displayFields, changeDisplayColumns]
  );

  const handleAddToQuery = useCallback(
    (field: string, isDisplay: boolean) => {
      addToQuery(
        {
          label: isDisplay ? DEFAULT_FIELDS_MAP[field] || field : field
        },
        'field'
      );
    },
    [addToQuery]
  );

  // 点击top值添加到查询
  const handleTopValueClick = useCallback(
    (field: string, value: string) => {
      addToQuery(
        {
          label: field,
          value: value
        },
        'value'
      );
    },
    [addToQuery]
  );

  // 渲染Top5值列表
  const renderTopValues = (field: string) => {
    const isLoading = loadingFields.has(field);
    const topValues = fieldTopValues[field] || [];

    if (isLoading) {
      return (
        <div className={searchStyle.topValuesLoading}>
          <Spin size="small" />
        </div>
      );
    }

    if (topValues.length === 0) {
      return <div className={searchStyle.topValuesEmpty}>--</div>;
    }

    return (
      <div className={searchStyle.topValuesList}>
        {topValues.map((item, index) => (
          <CustomPopover
            key={index}
            title={`${field} = ${item.value || '(empty)'}`}
            content={(onClose) => (
              <ul>
                <li>
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      onClose();
                      handleTopValueClick(field, item.value);
                    }}
                  >
                    {t('log.search.addToQuery')}
                  </Button>
                </li>
              </ul>
            )}
          >
            <div className={searchStyle.topValueItem}>
              <div className={searchStyle.topValueContent}>
                <EllipsisWithTooltip
                  className={searchStyle.topValueText}
                  text={item.value || '(empty)'}
                />
                <span className={searchStyle.topValueCount}>{item.count}</span>
                <span className={searchStyle.topValuePercent}>
                  {(item.ratio * 100).toFixed(2)}%
                </span>
              </div>
              <Progress
                percent={item.ratio * 100}
                showInfo={false}
                strokeColor="var(--color-primary)"
                trailColor="var(--color-fill-2)"
                className={searchStyle.topValueProgress}
              />
            </div>
          </CustomPopover>
        ))}
      </div>
    );
  };

  // 渲染可选字段项（用于虚拟列表）
  const renderHiddenFieldItem = (field: string) => {
    const isExpanded = expandedFields.has(field);
    const showExpandBtn = shouldShowExpandButton(field);

    return (
      <div
        className={`${searchStyle.listItem} ${isExpanded ? searchStyle.expanded : ''}`}
      >
        <div className={searchStyle.fieldHeader}>
          <div className="flex items-center flex-1 min-w-0">
            {showExpandBtn ? (
              <span
                className={searchStyle.expandIcon}
                onClick={(e) => toggleFieldExpand(field, e)}
              >
                {isExpanded ? (
                  <CaretDownFilled style={{ fontSize: 10 }} />
                ) : (
                  <CaretRightFilled style={{ fontSize: 10 }} />
                )}
              </span>
            ) : (
              <span className={searchStyle.expandIconPlaceholder} />
            )}
            <CustomPopover
              title={field}
              content={(onClose) => (
                <ul>
                  <li>
                    <Button
                      type="link"
                      size="small"
                      onClick={() => {
                        onClose();
                        handleAddToQuery(field, false);
                      }}
                    >
                      {t('log.search.addToQuery')}
                    </Button>
                  </li>
                </ul>
              )}
            >
              <div className="flex">
                <EllipsisWithTooltip
                  className={`w-[150px] overflow-hidden text-ellipsis whitespace-nowrap ${searchStyle.label}`}
                  text={field}
                />
                <MoreOutlined
                  className={`${searchStyle.operate} cursor-pointer`}
                />
              </div>
            </CustomPopover>
          </div>
          <PlusOutlined
            className={`${searchStyle.operate} ml-[4px] cursor-pointer scale-[0.8]`}
            onClick={() => operateFields('add', field)}
          />
        </div>
        {isExpanded && renderTopValues(field)}
      </div>
    );
  };

  const hasData =
    filteredDisplayFields.length > 0 || filteredHiddenFields.length > 0;

  return (
    <div className={`${searchStyle.fieldTree} ${className}`}>
      <Input
        allowClear
        placeholder={t('common.searchPlaceHolder')}
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
      />
      <div className={searchStyle.fields} style={style}>
        {!hasData ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className={searchStyle.displayFields}>
            {/* 表格展示字段（带拖拽排序） */}
            {filteredDisplayFields.length > 0 && (
              <>
                <div className={searchStyle.title}>
                  {t('log.search.displayFields')}
                </div>
                <ul className={searchStyle.fieldList}>
                  {filteredDisplayFields.map((field, index) => {
                    const isDefault = DEFAULT_FIELDS.includes(field);
                    const isDragging = draggedIndex === index;
                    const isExpanded = expandedFields.has(field);
                    const showExpandBtn = shouldShowExpandButton(field);

                    return (
                      <li
                        key={field}
                        className={`${searchStyle.listItem} ${isExpanded ? searchStyle.expanded : ''}`}
                        draggable={!isExpanded}
                        onDragStart={(e) => handleDragStart(e, index)}
                        onDragEnd={handleDragEnd}
                        onDragOver={handleDragOver}
                        onDrop={(e) => handleDrop(e, index)}
                        style={{
                          opacity: isDragging ? 0.5 : 1
                        }}
                      >
                        <div className={searchStyle.fieldHeader}>
                          <div className="flex items-center flex-1 min-w-0">
                            {!isExpanded && (
                              <HolderOutlined
                                className={`${searchStyle.dragHandle} cursor-grab mr-[4px]`}
                              />
                            )}
                            {showExpandBtn ? (
                              <span
                                className={searchStyle.expandIcon}
                                onClick={(e) => toggleFieldExpand(field, e)}
                              >
                                {isExpanded ? (
                                  <CaretDownFilled style={{ fontSize: 10 }} />
                                ) : (
                                  <CaretRightFilled style={{ fontSize: 10 }} />
                                )}
                              </span>
                            ) : (
                              <span
                                className={searchStyle.expandIconPlaceholder}
                              />
                            )}
                            <CustomPopover
                              title={field}
                              content={(onClose) => (
                                <ul>
                                  <li>
                                    <Button
                                      type="link"
                                      size="small"
                                      onClick={() => {
                                        onClose();
                                        handleAddToQuery(field, true);
                                      }}
                                    >
                                      {t('log.search.addToQuery')}
                                    </Button>
                                  </li>
                                </ul>
                              )}
                            >
                              <div className="flex items-center">
                                <EllipsisWithTooltip
                                  className={`w-[130px] overflow-hidden text-ellipsis whitespace-nowrap ${searchStyle.label}`}
                                  text={field}
                                />
                                <MoreOutlined
                                  className={`${searchStyle.operate} cursor-pointer`}
                                />
                              </div>
                            </CustomPopover>
                          </div>
                          {!isDefault && (
                            <CloseOutlined
                              className={`${searchStyle.operate} ml-[4px] cursor-pointer scale-[0.8]`}
                              onClick={() => operateFields('reduce', field)}
                            />
                          )}
                        </div>
                        {isExpanded && renderTopValues(field)}
                      </li>
                    );
                  })}
                </ul>
              </>
            )}

            {/* 可选字段（使用 rc-virtual-list） */}
            {filteredHiddenFields.length > 0 && (
              <>
                <div
                  className={searchStyle.title}
                  style={{
                    marginTop: filteredDisplayFields.length > 0 ? 12 : 0
                  }}
                >
                  {t('log.search.hiddenFields')}
                </div>
                <VirtualList
                  data={filteredHiddenFields}
                  height={hiddenFieldsContainerHeight}
                  itemHeight={ITEM_HEIGHT}
                  itemKey={(item) => item}
                >
                  {(field) => renderHiddenFieldItem(field)}
                </VirtualList>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default FieldList;
