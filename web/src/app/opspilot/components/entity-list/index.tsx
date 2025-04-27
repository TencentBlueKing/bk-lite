'use client';

import React, { useState, useEffect } from 'react';
import { Input, message, Spin, Modal, Select, Space } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import Icon from '@/components/icon';
import styles from '@/app/opspilot/styles/common.module.scss';
import PermissionWrapper from '@/components/permission';

const { Search } = Input;

interface EntityListProps<T> {
  endpoint: string;
  CardComponent: React.FC<any>;
  ModifyModalComponent: React.FC<any>;
  itemTypeSingle: string;
  beforeDelete?: (item: T, deleteCallback: () => void) => void;
  onCreateFromTemplate?: (itemType: string) => void;
}

const EntityList = <T,>({ endpoint, CardComponent, ModifyModalComponent, itemTypeSingle, beforeDelete, onCreateFromTemplate }: EntityListProps<T>) => {
  const { t } = useTranslation();
  const { get, post, patch, del } = useApiClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [items, setItems] = useState<T[]>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingItem, setEditingItem] = useState<null | T>(null);
  const [loading, setLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);

  const typeOptions = [
    { key: 2, title: t('skill.form.qaType') },
    { key: 1, title: t('skill.form.toolsType') },
  ];

  const handleTypeChange = (value: string | undefined) => {
    setSelectedType(value);
  };

  useEffect(() => {
    fetchItems();
  }, [get]);

  const fetchItems = async () => {
    setLoading(true);
    try {
      const data = await get(`${endpoint}`);
      setItems(Array.isArray(data) ? data : []);
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

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
        fetchItems();
        message.success(t('common.updateSuccess'));
      } else {
        await post(`${endpoint}`, params);
        fetchItems();
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
        fetchItems();
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
          fetchItems();
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

  const filteredItems = items.filter(item =>
    (item as any).name?.toLowerCase().includes(searchTerm.toLowerCase()) &&
    (!selectedType || (item as any).skill_type === selectedType)
  );

  return (
    <div className="w-full h-full">
      <div className="flex justify-end mb-4">
        {itemTypeSingle === 'skill' ? (
          <Space.Compact>
            <Select
              allowClear
              placeholder={t('common.select')}
              className="w-40"
              onChange={handleTypeChange}
              options={typeOptions.map(option => ({ value: option.key, label: option.title }))}
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
          {filteredItems.map((item, index) => (
            <CardComponent
              key={(item as any).id}
              {...item}
              index={index}
              onMenuClick={handleMenuClick}
            />
          ))}
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
