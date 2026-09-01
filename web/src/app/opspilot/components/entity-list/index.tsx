'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Dropdown, Input, message, Spin, Modal, Select, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import PermissionWrapper from '@/components/permission';
import OpsPilotListPageHeader from '@/app/opspilot/components/opspilot-list-page-header';
import OpsPilotCardGridSkeleton from '@/app/opspilot/components/opspilot-card-grid-skeleton';

const { Search } = Input;

interface TypeConfig {
  options: { key: number; title: string }[];
  searchField: string;
}

interface EntityListProps<T> {
  endpoint: string;
  queryParams?: Record<string, any>;
  CardComponent: React.FC<any>;
  ModifyModalComponent: React.FC<any>;
  itemTypeSingle: string;
  typeConfig?: TypeConfig;
  beforeDelete?: (item: T, deleteCallback: () => void) => void;
  onCreateFromTemplate?: (itemType: string) => void;
  onTogglePin?: (item: T) => Promise<void>;
  pageSize?: number;
  pageTitle?: string;
  pageDescription?: string;
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
  typeConfig,
  beforeDelete,
  onCreateFromTemplate,
  onTogglePin,
  pageSize = 20,
  pageTitle,
  pageDescription,
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

  const openCreateBlank = () => {
    setIsModalVisible(true);
    setEditingItem(null);
  };

  const createAction =
    itemTypeSingle === 'skill' && onCreateFromTemplate ? (
      <PermissionWrapper requiredPermissions={['Add']}>
        <Dropdown
          menu={{
            items: [
              {
                key: 'blank',
                label: t('skill.createBlankAgent'),
                onClick: openCreateBlank,
              },
              {
                key: 'template',
                label: t('skill.createFromTemplate'),
                onClick: handleCreateFromTemplate,
              },
            ],
          }}
          trigger={['click']}
        >
          <Button type="primary" icon={<PlusOutlined />}>
            {t('common.new')}
          </Button>
        </Dropdown>
      </PermissionWrapper>
    ) : (
      <PermissionWrapper requiredPermissions={['Add']}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateBlank}>
          {t('common.new')}
        </Button>
      </PermissionWrapper>
    );

  return (
    <div className="w-full h-full">
      {pageTitle ? (
        <OpsPilotListPageHeader
          title={pageTitle}
          description={pageDescription}
          actions={
            <>
              {currentTypeOptions.length > 0 ? (
                <Space.Compact>
                  <Select
                    mode="multiple"
                    allowClear
                    placeholder={t('common.select')}
                    className="w-40"
                    onChange={handleTypeChange}
                    options={currentTypeOptions.map((option) => ({
                      value: option.key,
                      label: option.title,
                    }))}
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
              {createAction}
            </>
          }
        />
      ) : (
        <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
          {currentTypeOptions.length > 0 ? (
            <Space.Compact>
              <Select
                mode="multiple"
                allowClear
                placeholder={t('common.select')}
                className="w-40"
                onChange={handleTypeChange}
                options={currentTypeOptions.map((option) => ({
                  value: option.key,
                  label: option.title,
                }))}
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
          {createAction}
        </div>
      )}
      {loading ? (
        <OpsPilotCardGridSkeleton />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
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
        </>
      )}
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
