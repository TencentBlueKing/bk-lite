'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Input, message, Spin, Modal, Select, Space } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import styles from '@/app/opspilot/styles/common.module.scss';
import PermissionWrapper from '@/components/permission';

const { Search } = Input;

interface EntityListProps<T> {
  endpoint: string;
  queryParams?: Record<string, any>;
  CardComponent: React.FC<any>;
  ModifyModalComponent: React.FC<any>;
  itemTypeSingle: string;
  beforeDelete?: (item: T, deleteCallback: () => void) => void;
  onCreateFromTemplate?: (itemType: string) => void;
  pageSize?: number;
}

interface ApiResponse<T> {
  count: number;
  items: T[];
}

const EntityList = <T,>({ 
  endpoint, 
  queryParams = {}, 
  CardComponent, 
  ModifyModalComponent, 
  itemTypeSingle, 
  beforeDelete, 
  onCreateFromTemplate,
  pageSize = 20
}: EntityListProps<T>) => {
  const { t } = useTranslation();
  const { get, post, patch, del } = useApiClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [items, setItems] = useState<T[]>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingItem, setEditingItem] = useState<null | T>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedTypes, setSelectedTypes] = useState<number[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const observer = useRef<IntersectionObserver>();
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const isFetching = useRef(false);

  const getTypeConfig = () => {
    if (itemTypeSingle === 'skill') {
      return {
        options: [
          { key: 2, title: t('skill.form.qaTag') },
          { key: 1, title: t('skill.form.toolsTag') },
          { key: 3, title: t('skill.form.planTag') },
          { key: 4, title: t('skill.form.complexTag') }
        ],
        searchField: 'skill_type'
      };
    } else if (itemTypeSingle === 'studio') {
      return {
        options: [
          { key: 1, title: t('studio.pilot') },
          { key: 2, title: t('studio.lobeChat') },
          { key: 3, title: t('studio.chatflow') }
        ],
        searchField: 'bot_type'
      };
    }
    return { options: [], searchField: '' };
  };

  const { options: currentTypeOptions, searchField } = getTypeConfig();

  const handleTypeChange = (values: number[]) => {
    setSelectedTypes(values || []);
    setCurrentPage(1);
    setItems([]);
    setHasMore(true);
    setTimeout(() => {
      fetchItems(true);
    }, 0);
  };

  const fetchItems = useCallback(async (reset = false) => {
    if (isFetching.current || (!reset && !hasMore)) return;
    
    isFetching.current = true;
    
    if (reset) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }
    
    try {
      const params = {
        ...queryParams,
        page: reset ? 1 : currentPage,
        page_size: pageSize,
        name: searchTerm,
        ...(selectedTypes.length > 0 && { [searchField]: selectedTypes.join(',') })
      };
      
      const queryString = new URLSearchParams(
        Object.entries(params).reduce((acc, [key, value]) => {
          if (value !== undefined && value !== null) {
            acc[key] = value.toString();
          }
          return acc;
        }, {} as Record<string, string>)
      ).toString();
      const response = await get<ApiResponse<T>>(`${endpoint}?${queryString}`);
      
      if (reset) {
        setItems(response.items || []);
        setCurrentPage(1);
      } else {
        setItems(prevItems => [...prevItems, ...(response.items || [])]);
      }
      
      const hasMoreData = (reset ? 1 : currentPage) * pageSize < (response.count || 0);
      setHasMore(hasMoreData);
      
      if (hasMoreData) {
        setCurrentPage(prev => prev + 1);
      }
    } catch (error) {
      console.error('API request failed:', error);
      message.error(t('common.fetchFailed'));
      if (reset) {
        setItems([]);
        setCurrentPage(1);
      }
      setHasMore(false);
    } finally {
      isFetching.current = false;
      if (reset) {
        setLoading(false);
      } else {
        setLoadingMore(false);
      }
    }
  }, [currentPage, pageSize, searchTerm, selectedTypes, hasMore, searchField]);

  useEffect(() => {
    setCurrentPage(1);
    setItems([]);
    setHasMore(true);
    fetchItems(true);
  }, [searchTerm, selectedTypes]);

  useEffect(() => {
    if (!loadMoreRef.current || loading || loadingMore || !hasMore) return;

    const observerCallback: IntersectionObserverCallback = (entries) => {
      if (entries[0].isIntersecting && !isFetching.current) {
        fetchItems();
      }
    };

    observer.current = new IntersectionObserver(observerCallback, {
      root: null,
      rootMargin: '100px',
      threshold: 0.1,
    });

    observer.current.observe(loadMoreRef.current);

    return () => {
      if (observer.current) {
        observer.current.disconnect();
      }
    };
  }, [loading, loadingMore, hasMore]);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
  };

  const handleAddItem = async (values: T) => {
    const params = {
      ...values
    }
    try {
      if (editingItem) {
        await patch(`${endpoint}${(editingItem as any).id}/`, params);
        fetchItems(true);
        message.success(t('common.updateSuccess'));
      } else {
        await post(`${endpoint}`, params);
        fetchItems(true);
        message.success(t('common.addSuccess'));
      }
      setIsModalVisible(false);
      setEditingItem(null);
    } catch {
      message.error(t('common.saveFailed'));
    }
  };

  const handleDelete = async (item: T) => {
    if (beforeDelete) {
      beforeDelete(item, async () => {
        fetchItems(true);
      });
    } else {
      deleteItem(item);
    }
  };

  const deleteItem = async (item: T) => {
    Modal.confirm({
      title: t(`${itemTypeSingle}.deleteConfirm`),
      onOk: async () => {
        try {
          await del(`${endpoint}${(item as any).id}/`);
          fetchItems(true);
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const handleMenuClick = (action: string, item: T) => {
    if (action === 'edit') {
      setEditingItem(item);
      setIsModalVisible(true);
    } else if (action === 'delete') {
      handleDelete(item);
    }
  };

  const handleCreateFromTemplate = () => {
    if (onCreateFromTemplate) {
      onCreateFromTemplate(itemTypeSingle);
    }
  };

  return (
    <div className="w-full h-full">
      <div className="flex justify-end mb-4">
        {(itemTypeSingle === 'skill' || itemTypeSingle === 'studio') ? (
          <Space.Compact>
            <Select
              mode="multiple"
              allowClear
              placeholder={t('common.select')}
              className="w-40"
              onChange={handleTypeChange}
              options={currentTypeOptions.map(option => ({ value: option.key, label: option.title }))}
              maxTagCount="responsive"
            />
            <Search
              allowClear
              enterButton
              placeholder={`${t('common.search')}...`}
              className="w-60"
              onSearch={handleSearch}
            />
          </Space.Compact>
        ) : (
          <Search
            allowClear
            enterButton
            placeholder={`${t('common.search')}...`}
            className="w-60"
            onSearch={handleSearch}
          />
        )}
      </div>
      <Spin spinning={loading}>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
          {itemTypeSingle === 'skill' ? (
            <PermissionWrapper
              requiredPermissions={['Add']}
              className={`shadow-md p-4 rounded-xl flex items-center justify-center cursor-pointer ${styles.addNew}`}
            >
              <div className="w-full h-full flex flex-col items-center justify-center min-h-[150px] pl-10">
                <div
                  className="w-full flex items-center justify-start cursor-pointer hover:text-[var(--color-primary)]"
                  onClick={() => { setIsModalVisible(true); setEditingItem(null); }}
                >
                  <div className="flex items-start mb-4">
                    <Icon type="xinzeng1" className="text-xl mr-2" />
                    <div className="text-left">{t('skill.createBlankAgent')}</div>
                  </div>
                </div>
                <div
                  className="w-full flex items-center justify-start cursor-pointer hover:text-[var(--color-primary)]"
                  onClick={handleCreateFromTemplate}
                >
                  <div className="flex items-start">
                    <Icon type="chuangjianpushu-xianxing" className="text-xl mr-2" />
                    <div className="text-left">{t('skill.createFromTemplate')}</div>
                  </div>
                </div>
              </div>
            </PermissionWrapper>
          ) : (
            <PermissionWrapper
              requiredPermissions={['Add']}
              className={`shadow-md p-4 rounded-xl flex items-center justify-center cursor-pointer ${styles.addNew}`}
            >
              <div
                className="w-full h-full flex items-center justify-center min-h-[150px]"
                onClick={() => { setIsModalVisible(true); setEditingItem(null); }}
              >
                <div className="text-center">
                  <div className='2xl'>+</div>
                  <div className="mt-2">{t('common.addNew')}</div>
                </div>
              </div>
            </PermissionWrapper>
          )}
          {items.map((item, index) => (
            <CardComponent
              key={(item as any).id || index}
              {...item}
              index={index}
              onMenuClick={handleMenuClick}
            />
          ))}
        </div>
        <div ref={loadMoreRef} className="w-full h-6 flex items-center justify-center">
          {loadingMore && <Spin size="small" />}
          {/* {!hasMore && items.length > 0 && (
            <div className="text-gray-500 text-xs py-4">
              {t('common.noMoreData')} (共 {totalCount} 条)
            </div>
          )} */}
        </div>
      </Spin>
      <ModifyModalComponent
        visible={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        onConfirm={handleAddItem}
        initialValues={editingItem}
      />
    </div>
  );
};

export default EntityList;