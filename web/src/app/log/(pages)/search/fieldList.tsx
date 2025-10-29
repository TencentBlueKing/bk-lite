'use client';
import React, { useState, useMemo, useRef, useCallback } from 'react';
import { CloseOutlined, MoreOutlined, PlusOutlined } from '@ant-design/icons';
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
  message: '_msg',
};

// 虚拟滚动配置
const ITEM_HEIGHT = 32; // 每个列表项的高度
const SPACER_HEIGHT = 12; // 间距项的高度
const BUFFER_SIZE = 8; // 增加缓冲区大小，减少空白闪烁
const OVERSCAN = 3; // 额外的预渲染项目数

interface VirtualListItem {
  id: string;
  type: 'section-title' | 'field-item';
  data: any;
  section: 'display' | 'hidden';
  height?: number; // 动态高度
}

const FieldList: React.FC<FieldListProps> = ({
  fields,
  className = '',
  style = {},
  addToQuery,
  changeDisplayColumns,
}) => {
  const { t } = useTranslation();
  const [searchText, setSearchText] = useState<string>('');
  const [displayFields, setDisplayFields] = useState<string[]>(
    localStorage.getItem('logSearchFields')
      ? JSON.parse(localStorage.getItem('logSearchFields') || '[]')
      : DEFAULT_FIELDS
  );

  // 虚拟滚动相关状态
  const [scrollTop, setScrollTop] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const CONTAINER_HEIGHT = +(style.height || '').replace('px', '') || 400; // 容器高度

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

  // 构建虚拟列表数据
  const virtualListData = useMemo(() => {
    const items: VirtualListItem[] = [];

    // 添加显示字段部分
    if (filteredDisplayFields.length > 0) {
      items.push({
        id: 'display-title',
        type: 'section-title',
        data: { title: t('log.search.displayFields') },
        section: 'display',
        height: ITEM_HEIGHT,
      });

      filteredDisplayFields.forEach((field, index) => {
        items.push({
          id: `display-${field}-${index}`,
          type: 'field-item',
          data: { field, isDisplay: true },
          section: 'display',
          height: ITEM_HEIGHT,
        });
      });
    }

    // 添加隐藏字段部分
    if (filteredHiddenFields.length > 0) {
      // 如果有显示字段，在隐藏字段标题前加一个空白项来实现间距
      if (filteredDisplayFields.length > 0) {
        items.push({
          id: 'spacer',
          type: 'section-title',
          data: { title: '', isSpacer: true },
          section: 'hidden',
          height: SPACER_HEIGHT,
        });
      }

      items.push({
        id: 'hidden-title',
        type: 'section-title',
        data: { title: t('log.search.hiddenFields') },
        section: 'hidden',
        height: ITEM_HEIGHT,
      });

      filteredHiddenFields.forEach((field, index) => {
        items.push({
          id: `hidden-${field}-${index}`,
          type: 'field-item',
          data: { field, isDisplay: false },
          section: 'hidden',
          height: ITEM_HEIGHT,
        });
      });
    }

    return items;
  }, [filteredDisplayFields, filteredHiddenFields, t]);

  // 计算每个项目的累积位置
  const itemPositions = useMemo(() => {
    const positions: number[] = [];
    let currentTop = 0;

    virtualListData.forEach((item, index) => {
      positions[index] = currentTop;
      currentTop += item.height || ITEM_HEIGHT;
    });

    return positions;
  }, [virtualListData]);

  const totalHeight = useMemo(() => {
    return virtualListData.reduce(
      (sum, item) => sum + (item.height || ITEM_HEIGHT),
      0
    );
  }, [virtualListData]);

  // 使用二分查找优化可见项计算
  const findItemIndex = useCallback((targetY: number, positions: number[]) => {
    let left = 0;
    let right = positions.length - 1;

    while (left <= right) {
      const mid = Math.floor((left + right) / 2);
      const midPosition = positions[mid];

      if (midPosition === targetY) {
        return mid;
      } else if (midPosition < targetY) {
        left = mid + 1;
      } else {
        right = mid - 1;
      }
    }

    return Math.max(0, right);
  }, []);

  // 计算可见项目 - 优化版本
  const visibleItems = useMemo(() => {
    if (itemPositions.length === 0) return [];

    // 计算更大的缓冲区，减少快速滚动时的空白
    const bufferHeight = BUFFER_SIZE * ITEM_HEIGHT;
    const overscanHeight = OVERSCAN * ITEM_HEIGHT;

    const startY = Math.max(0, scrollTop - bufferHeight - overscanHeight);
    const endY = scrollTop + CONTAINER_HEIGHT + bufferHeight + overscanHeight;

    // 使用二分查找快速定位起始索引
    const startIndex = findItemIndex(startY, itemPositions);

    const visibleItemsData: Array<
      VirtualListItem & { index: number; top: number }
    > = [];

    // 从起始索引开始，只遍历可能可见的项目
    for (let i = startIndex; i < virtualListData.length; i++) {
      const itemTop = itemPositions[i];
      const itemBottom = itemTop + (virtualListData[i].height || ITEM_HEIGHT);

      // 如果项目完全超出可见区域，停止遍历
      if (itemTop > endY) {
        break;
      }

      // 判断项目是否在扩展的可见区域内
      if (itemBottom >= startY) {
        visibleItemsData.push({
          ...virtualListData[i],
          index: i,
          top: itemTop,
        });
      }
    }

    return visibleItemsData;
  }, [
    virtualListData,
    itemPositions,
    scrollTop,
    CONTAINER_HEIGHT,
    findItemIndex,
  ]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const newScrollTop = e.currentTarget.scrollTop;
    setScrollTop(newScrollTop);
  }, []);

  const operateFields = (type: string, field: string) => {
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
  };

  // 渲染列表项
  const renderListItem = (
    item: VirtualListItem & { index: number; top: number }
  ) => {
    const itemHeight = item.height || ITEM_HEIGHT;

    if (item.type === 'section-title') {
      // 如果是间距项，返回空的 div
      if (item.data.isSpacer) {
        return (
          <div
            key={item.id}
            style={{
              position: 'absolute',
              top: item.top,
              left: 0,
              right: 0,
              height: itemHeight,
            }}
          />
        );
      }

      return (
        <div
          key={item.id}
          className={searchStyle.title}
          style={{
            position: 'absolute',
            top: item.top,
            left: 0,
            right: 0,
            height: itemHeight,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          {item.data.title}
        </div>
      );
    }

    const { field, isDisplay } = item.data;

    return (
      <li
        key={item.id}
        className={searchStyle.listItem}
        style={{
          position: 'absolute',
          top: item.top,
          left: 0,
          right: 0,
          height: itemHeight,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
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
                    addToQuery(
                      {
                        label: isDisplay
                          ? DEFAULT_FIELDS_MAP[field] || field
                          : field,
                      },
                      'field'
                    );
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
              text={field}
            />
            <MoreOutlined className={`${searchStyle.operate} cursor-pointer`} />
          </div>
        </CustomPopover>
        <div>
          {isDisplay ? (
            !DEFAULT_FIELDS.includes(field) && (
              <CloseOutlined
                className={`${searchStyle.operate} ml-[4px] cursor-pointer scale-[0.8]`}
                onClick={() => {
                  operateFields('reduce', field);
                }}
              />
            )
          ) : (
            <PlusOutlined
              className={`${searchStyle.operate} ml-[4px] cursor-pointer scale-[0.8]`}
              onClick={() => {
                operateFields('add', field);
              }}
            />
          )}
        </div>
      </li>
    );
  };

  return (
    <div className={`${searchStyle.fieldTree} ${className}`}>
      <Input
        allowClear
        placeholder={t('common.searchPlaceHolder')}
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
      ></Input>
      <div className={searchStyle.fields} style={style}>
        {virtualListData.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className={searchStyle.displayFields}>
            <div
              ref={containerRef}
              style={{
                height: Math.min(CONTAINER_HEIGHT, totalHeight),
                overflow: 'auto',
                position: 'relative',
              }}
              onScroll={handleScroll}
            >
              <ul
                className={searchStyle.fieldList}
                style={{
                  height: totalHeight,
                  position: 'relative',
                  margin: 0,
                  padding: 0,
                  listStyle: 'none',
                }}
              >
                {visibleItems.map(renderListItem)}
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default FieldList;
