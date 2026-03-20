'use client';
import React, { useState, useMemo, useRef, useCallback } from 'react';
import {
  CloseOutlined,
  MoreOutlined,
  PlusOutlined,
  HolderOutlined
} from '@ant-design/icons';
import { Input, Empty, Button } from 'antd';
import CustomPopover from './customPopover';
import { useTranslation } from '@/utils/i18n';
import searchStyle from './index.module.scss';
import { FieldListProps } from '@/app/log/types/search';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { cloneDeep } from 'lodash';

const DEFAULT_FIELDS = ['timestamp', 'message'];
const DEFAULT_FIELDS_MAP: Record<string, string> = {
  timestamp: '_time',
  message: '_msg'
};

// 虚拟滚动配置（仅用于可选字段）
const ITEM_HEIGHT = 32;
const BUFFER_SIZE = 8;
const OVERSCAN = 3;

const FieldList: React.FC<FieldListProps> = ({
  fields,
  className = '',
  style = {},
  addToQuery,
  changeDisplayColumns
}) => {
  const { t } = useTranslation();
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

  // 虚拟滚动相关状态（仅用于可选字段）
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
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

  // 计算可选字段区域的高度
  const displayFieldsHeight = useMemo(() => {
    return ITEM_HEIGHT + filteredDisplayFields.length * ITEM_HEIGHT + 12;
  }, [filteredDisplayFields.length]);

  const hiddenFieldsContainerHeight = useMemo(() => {
    const available = CONTAINER_HEIGHT - displayFieldsHeight - ITEM_HEIGHT;
    return Math.max(100, available);
  }, [CONTAINER_HEIGHT, displayFieldsHeight]);

  const totalHiddenHeight = filteredHiddenFields.length * ITEM_HEIGHT;

  // 计算可见的可选字段项目
  const visibleHiddenItems = useMemo(() => {
    if (filteredHiddenFields.length === 0) return [];

    const bufferHeight = BUFFER_SIZE * ITEM_HEIGHT;
    const overscanHeight = OVERSCAN * ITEM_HEIGHT;

    const startY = Math.max(0, scrollTop - bufferHeight - overscanHeight);
    const endY =
      scrollTop + hiddenFieldsContainerHeight + bufferHeight + overscanHeight;

    const startIndex = Math.max(0, Math.floor(startY / ITEM_HEIGHT));
    const endIndex = Math.min(
      filteredHiddenFields.length - 1,
      Math.ceil(endY / ITEM_HEIGHT)
    );

    const items: Array<{ field: string; index: number; top: number }> = [];
    for (let i = startIndex; i <= endIndex; i++) {
      items.push({
        field: filteredHiddenFields[i],
        index: i,
        top: i * ITEM_HEIGHT
      });
    }

    return items;
  }, [filteredHiddenFields, scrollTop, hiddenFieldsContainerHeight]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
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
      // 添加拖拽时的样式
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

                    return (
                      <li
                        key={field}
                        className={searchStyle.listItem}
                        draggable={!searchText} // 搜索时禁用拖拽
                        onDragStart={(e) => handleDragStart(e, index)}
                        onDragEnd={handleDragEnd}
                        onDragOver={handleDragOver}
                        onDrop={(e) => handleDrop(e, index)}
                        style={{
                          opacity: isDragging ? 0.5 : 1
                        }}
                      >
                        <div className="flex items-center flex-1 min-w-0">
                          {!searchText && (
                            <HolderOutlined
                              className={`${searchStyle.dragHandle} cursor-grab mr-[4px]`}
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
                                className={`w-[100px] overflow-hidden text-ellipsis whitespace-nowrap ${searchStyle.label}`}
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
                      </li>
                    );
                  })}
                </ul>
              </>
            )}

            {/* 可选字段（虚拟滚动） */}
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
                <div
                  ref={containerRef}
                  style={{
                    height: Math.min(
                      hiddenFieldsContainerHeight,
                      totalHiddenHeight
                    ),
                    overflow: 'auto',
                    position: 'relative'
                  }}
                  onScroll={handleScroll}
                >
                  <ul
                    className={searchStyle.fieldList}
                    style={{
                      height: totalHiddenHeight,
                      position: 'relative',
                      margin: 0,
                      padding: 0,
                      listStyle: 'none'
                    }}
                  >
                    {visibleHiddenItems.map((item) => (
                      <li
                        key={item.field}
                        className={searchStyle.listItem}
                        style={{
                          position: 'absolute',
                          top: item.top,
                          left: 0,
                          right: 0,
                          height: ITEM_HEIGHT,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between'
                        }}
                      >
                        <CustomPopover
                          title={item.field}
                          content={(onClose) => (
                            <ul>
                              <li>
                                <Button
                                  type="link"
                                  size="small"
                                  onClick={() => {
                                    onClose();
                                    handleAddToQuery(item.field, false);
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
                              className={`w-[120px] overflow-hidden text-ellipsis whitespace-nowrap ${searchStyle.label}`}
                              text={item.field}
                            />
                            <MoreOutlined
                              className={`${searchStyle.operate} cursor-pointer`}
                            />
                          </div>
                        </CustomPopover>
                        <PlusOutlined
                          className={`${searchStyle.operate} ml-[4px] cursor-pointer scale-[0.8]`}
                          onClick={() => operateFields('add', item.field)}
                        />
                      </li>
                    ))}
                  </ul>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default FieldList;
