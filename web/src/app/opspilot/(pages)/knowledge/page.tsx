'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Input, Dropdown, Menu, Modal, message, Spin } from 'antd';
import Icon from '@/components/icon';
import { KnowledgeValues, Card } from '@/app/opspilot/types/knowledge';
import ModifyKnowledgeModal from './modifyKnowledge';
import PermissionWrapper from '@/components/permission';
import styles from '@/app/opspilot/styles/common.module.scss';
import { useTranslation } from '@/utils/i18n';
import { getIconTypeByIndex } from '@/app/opspilot/utils/knowledgeBaseUtils';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { Search } = Input;

const KnowledgePage = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const { fetchKnowledgeBase, addKnowledge, updateKnowledge, deleteKnowledge } = useKnowledgeApi();
  const [searchTerm, setSearchTerm] = useState('');
  const [cards, setCards] = useState<Card[]>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingCard, setEditingCard] = useState<null | KnowledgeValues>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const isFetching = useRef(false);

  const fetchCards = useCallback(async (reset = false) => {
    if (isFetching.current || (!reset && !hasMore)) return;

    isFetching.current = true;

    if (reset) {
      setLoading(true);
    } else {
      setLoadingMore(true);
    }

    try {
      const pageToFetch = reset ? 1 : currentPage;
      const data = await fetchKnowledgeBase({
        page: pageToFetch,
        page_size: 20,
        search: searchTerm
      });

      const items = Array.isArray(data) ? data : (data.items || []);
      const totalCount = Array.isArray(data) ? data.length : (data.count || 0);

      if (reset) {
        setCards(items);
        setCurrentPage(1);
      } else {
        setCards(prev => [...prev, ...items]);
      }

      const hasMoreData = pageToFetch * 20 < totalCount;
      setHasMore(hasMoreData);

      if (hasMoreData) {
        setCurrentPage(pageToFetch + 1);
      }
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      isFetching.current = false;
      if (reset) {
        setLoading(false);
      } else {
        setLoadingMore(false);
      }
    }
  }, [currentPage, searchTerm, hasMore]);

  useEffect(() => {
    setCurrentPage(1);
    setCards([]);
    setHasMore(true);
    fetchCards(true);
  }, [searchTerm]);

  // Intersection Observer设置
  useEffect(() => {
    if (!loadMoreRef.current || loading || loadingMore || !hasMore) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isFetching.current) {
          fetchCards();
        }
      },
      {
        root: null,
        rootMargin: '100px',
        threshold: 0.1,
      }
    );

    observer.observe(loadMoreRef.current);

    return () => {
      observer.disconnect();
    };
  }, [loading, loadingMore, hasMore]);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
  };

  const handleAddKnowledge = async (values: KnowledgeValues) => {
    try {
      if (editingCard) {
        await updateKnowledge(editingCard.id, values);
        setCards(cards.map(card => card.id === editingCard?.id ? { ...card, ...values } : card));
        message.success(t('common.updateSuccess'));
      } else {
        const newCard = await addKnowledge(values);
        setCards([newCard, ...cards]);
        message.success(t('common.addSuccess'));
      }
      setIsModalVisible(false);
      setEditingCard(null);
    } catch {
      message.error(t('common.saveFailed'));
    }
  };

  const handleDelete = (cardId: number) => {
    Modal.confirm({
      title: `${t('knowledge.deleteConfirm')}`,
      onOk: async () => {
        try {
          await deleteKnowledge(cardId);
          setCards(cards.filter(card => card.id !== cardId));
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const handleMenuClick = (action: string, card: Card) => {
    if (action === 'edit') {
      setEditingCard(card);
      setIsModalVisible(true);
    } else if (action === 'delete') {
      handleDelete(card.id);
    }
  };

  const menu = (card: Card) => (
    <Menu className={`${styles.menuContainer}`}>
      <Menu.Item key="edit">
        <PermissionWrapper
          requiredPermissions={['Edit']}
          instPermissions={card.permissions}>
          <span className='block' onClick={() => handleMenuClick('edit', card)}>{t('common.edit')}</span>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="delete">
        <PermissionWrapper
          requiredPermissions={['Delete']}
          instPermissions={card.permissions}>
          <span className='block' onClick={() => handleMenuClick('delete', card)}>{t('common.delete')}</span>
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  );

  const filteredCards = cards.filter((card) =>
    card.name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="w-full">
      <div className="flex justify-end mb-4">
        <Search
          allowClear
          enterButton
          placeholder={`${t('common.search')}...`}
          className="w-60"
          onSearch={handleSearch}
        />
      </div>
      <Spin spinning={loading}>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
          <PermissionWrapper
            requiredPermissions={['Add']}
            className="p-4 rounded-xl flex items-center justify-center shadow-md cursor-pointer bg-[var(--color-bg)]"
          >
            <div
              className="w-full h-full flex items-center justify-center min-h-[120px]"
              onClick={() => { setIsModalVisible(true); setEditingCard(null); }}
            >
              <Icon type="tianjia" className="text-2xl" />
              <span className="ml-2">{t('common.addNew')}</span>
            </div>
          </PermissionWrapper>
          {filteredCards.map((card, index) => (
            <div
              key={card.id}
              className="p-4 rounded-xl relative shadow-md cursor-pointer bg-[var(--color-bg)]"
              onClick={() => router.push(`/opspilot/knowledge/detail?id=${card.id}&name=${card.name}&desc=${card.introduction}`)}
            >
              <div className="absolute top-6 right-2" onClick={(e) => e.stopPropagation()}>
                <Dropdown overlay={menu(card)} trigger={['click']} placement="bottomRight">
                  <div className="cursor-pointer">
                    <Icon type="sangedian-copy" className="text-xl" />
                  </div>
                </Dropdown>
              </div>
              <div className="flex items-center mb-2" style={{width: 'calc(100% - 10px)'}}>
                <div className="rounded-full">
                  <Icon type={getIconTypeByIndex(index)} className="text-4xl" />
                </div>
                <h3 className="ml-2 text-sm font-semibold truncate text-[var(--color-text-1)]" title={card.name}>
                  {card.name}
                </h3>
              </div>
              <p className="mt-3 mb-2 text-xs line-clamp-3 h-[50px] text-[var(--color-text-3)]">{card.introduction}</p>
              <div className="flex items-end justify-end text-[var(--color-text-4)] font-mini w-full text-right">
                <span>{t('knowledge.form.owner')}: {card.created_by} ｜ {t('knowledge.form.group')}: {Array.isArray(card.team_name) ? card.team_name.join(',') : '--'}</span>
              </div>
            </div>
          ))}
        </div>
        <div ref={loadMoreRef} className="w-full h-6 flex items-center justify-center">
          {loadingMore && <Spin size="small" />}
        </div>
      </Spin>
      <ModifyKnowledgeModal
        visible={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        onConfirm={handleAddKnowledge}
        initialValues={editingCard}
        isTraining={editingCard?.is_training || false}
      />
    </div>
  );
};

export default KnowledgePage;
