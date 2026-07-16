'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Input, message, Spin, Modal, Select, Space } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import styles from '@/app/opspilot/styles/common.module.scss';
import PermissionWrapper from '@/components/permission';

const { Search } = Input;

interface TypeConfig {
  options: { key: number; title: string }[];
  searchField: string;
}

export interface EntityManagementGridFetchParams {
  page: number;
  page_size: number;
  name: string;
  selectedTypes: number[];
  searchField: string;
  queryParams: Record<string, any>;
}

export interface EntityManagementGridApiResponse<T> {
  count: number;
  items: T[];
}

export interface EntityManagementGridDataSource<T> {
  fetchPage: (params: EntityManagementGridFetchParams) => Promise<EntityManagementGridApiResponse<T>>;
  createItem: (values: T) => Promise<unknown>;
  updateItem: (item: T, values: T) => Promise<unknown>;
  deleteItem: (item: T) => Promise<unknown>;
}

interface EntityManagementGridProps<T> {
  endpoint?: string;
  queryParams?: Record<string, any>;
  CardComponent: React.FC<any>;
  ModifyModalComponent: React.FC<any>;
  itemTypeSingle: string;
  typeConfig?: TypeConfig;
  beforeDelete?: (item: T, deleteCallback: () => void) => void;
  onCreateFromTemplate?: (itemType: string) => void;
  onTogglePin?: (item: T) => Promise<void>;
  pageSize?: number;
  dataSource?: EntityManagementGridDataSource<T>;
}

const EntityManagementGrid = <T,>({
  endpoint,
  queryParams = {},
  CardComponent,
  ModifyModalComponent,
  itemTypeSingle,
  typeConfig,
  beforeDelete,
  onCreateFromTemplate,
  onTogglePin,
  pageSize = 20,
  dataSource,
}: EntityManagementGridProps<T>) => {
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
  const observer = useRef<IntersectionObserver>(null as any);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const isFetching = useRef(false);
  const typeChangeTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (typeChangeTimerRef.current) clearTimeout(typeChangeTimerRef.current);
    };
  }, []);

  const getTypeConfig = (): TypeConfig => {
    if (typeConfig) return typeConfig;
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
    if (typeChangeTimerRef.current) clearTimeout(typeChangeTimerRef.current);
    typeChangeTimerRef.current = setTimeout(() => {
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
      const page = reset ? 1 : currentPage;

      let response: EntityManagementGridApiResponse<T>;

      if (dataSource) {
        response = await dataSource.fetchPage({
          page,
          page_size: pageSize,
          name: searchTerm,
          selectedTypes,
          searchField,
          queryParams,
        });
      } else {
        if (!endpoint) {
          throw new Error('EntityManagementGrid requires either endpoint or dataSource');
        }

        const params = {
          ...queryParams,
          page,
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

        response = await get<EntityManagementGridApiResponse<T>>(`${endpoint}?${queryString}`);
      }

      if (reset) {
        setItems(response.items || []);
        setCurrentPage(1);
      } else {
        setItems(prevItems => [...prevItems, ...(response.items || [])]);
      }

      const hasMoreData = page * pageSize < (response.count || 0);
      setHasMore(hasMoreData);

      if (hasMoreData) {
        setCurrentPage(page + 1);
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
  }, [currentPage, dataSource, endpoint, get, hasMore, pageSize, queryParams, searchField, searchTerm, selectedTypes, t]);

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
  }, [fetchItems, hasMore, loading, loadingMore]);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
  };

  const handleAddItem = async (values: T) => {
    try {
      if (editingItem) {
        if (dataSource) {
          await dataSource.updateItem(editingItem, values);
        } else {
          await patch(`${endpoint}${(editingItem as any).id}/`, values as any);
        }
        fetchItems(true);
        message.success(t('common.updateSuccess'));
      } else {
        if (dataSource) {
          await dataSource.createItem(values);
        } else {
          await post(`${endpoint}`, values as any);
        }
        fetchItems(true);
        message.success(t('common.addSuccess'));
      }
      setIsModalVisible(false);
      setEditingItem(null);
    } catch {
      message.error(t('common.saveFailed'));
    }
  };

  const runDeleteItem = async (item: T) => {
    if (dataSource) {
      await dataSource.deleteItem(item);
    } else {
      await del(`${endpoint}${(item as any).id}/`);
    }
  };

  const handleDelete = async (item: T) => {
    if (beforeDelete) {
      beforeDelete(item, async () => {
        fetchItems(true);
      });
    } else {
      Modal.confirm({
        title: t(`${itemTypeSingle}.deleteConfirm`),
        onOk: async () => {
          try {
            await runDeleteItem(item);
            fetchItems(true);
            message.success(t('common.delSuccess'));
          } catch {
            message.error(t('common.delFailed'));
          }
        },
      });
    }
  };

  const handleMenuClick = (action: string, item: T) => {
    if (action === 'edit') {
      setEditingItem(item);
      setIsModalVisible(true);
    } else if (action === 'delete') {
      handleDelete(item);
    } else if (action === 'pin') {
      handleTogglePin(item);
    }
  };

  const handleTogglePin = async (item: T) => {
    if (onTogglePin) {
      try {
        await onTogglePin(item);
        fetchItems(true);
      } catch {
        message.error(t('common.saveFailed'));
      }
    }
  };

  const handleCreateFromTemplate = () => {
    if (onCreateFromTemplate) {
      onCreateFromTemplate(itemTypeSingle);
    }
  };

  return (
    <div className="w-full h-full">
      <div className="mb-4 flex justify-end">
        {itemTypeSingle === 'skill' ? (
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
          {itemTypeSingle === 'skill' ? (
            <PermissionWrapper
              requiredPermissions={['Add']}
              className={`flex cursor-pointer items-center justify-center rounded-xl p-4 shadow-md ${styles.addNew}`}
            >
              <div className="flex min-h-37.5 h-full w-full flex-col justify-center pl-10">
                <div
                  className="flex w-full cursor-pointer items-center justify-start hover:text-(--color-primary)"
                  onClick={() => { setIsModalVisible(true); setEditingItem(null); }}
                >
                  <div className="mb-4 flex items-start">
                    <Icon type="xinzeng1" className="mr-2 text-xl" />
                    <div className="text-left">{t('skill.createBlankAgent')}</div>
                  </div>
                </div>
                <div
                  className="flex w-full cursor-pointer items-center justify-start hover:text-(--color-primary)"
                  onClick={handleCreateFromTemplate}
                >
                  <div className="flex items-start">
                    <Icon type="chuangjianpushu-xianxing" className="mr-2 text-xl" />
                    <div className="text-left">{t('skill.createFromTemplate')}</div>
                  </div>
                </div>
              </div>
            </PermissionWrapper>
          ) : (
            <PermissionWrapper
              requiredPermissions={['Add']}
              className={`flex cursor-pointer items-center justify-center rounded-xl p-4 shadow-md ${styles.addNew}`}
            >
              <div
                className="flex min-h-37.5 h-full w-full items-center justify-center"
                onClick={() => { setIsModalVisible(true); setEditingItem(null); }}
              >
                <div className="text-center">
                  <div className="text-2xl">+</div>
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
        <div ref={loadMoreRef} className="flex h-6 w-full items-center justify-center">
          {loadingMore && <Spin size="small" />}
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

export default EntityManagementGrid;
