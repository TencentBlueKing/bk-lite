'use client';
import React, { useState, useEffect } from 'react';
import { Card, Input, Spin, Pagination } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import ContentDrawer from '@/components/content-drawer';
import useContentDrawer from '@/app/opspilot/hooks/useContentDrawer';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

interface Paragraph {
  id: string;
  content: string;
}

const DocsResultPage: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [paragraphsState, setParagraphsState] = useState<Paragraph[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);
  const [totalItems, setTotalItems] = useState<number>(0);
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('knowledgeId') : null;
  const { fetchDocumentDetails } = useKnowledgeApi();

  const {
    drawerVisible,
    drawerContent,
    showDrawer,
    hideDrawer,
  } = useContentDrawer();

  const fetchData = async (page: number, pageSize: number, searchValue?: string) => {
    if (id) {
      setLoading(true);
      try {
        const { count, items } = await fetchDocumentDetails(id, page, pageSize, searchValue || '');
        setParagraphsState(items);
        setTotalItems(count);
      } catch (error) {
        console.error(`${t('common.errorFetch')}: ${error}`);
      } finally {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchData(currentPage, pageSize, searchTerm);
  }, [id]);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    setCurrentPage(1);
    fetchData(1, pageSize, value);
  };

  const handlePageChange = (page: number, pageSize?: number) => {
    setCurrentPage(page);
    if (pageSize) {
      setPageSize(pageSize);
    }
    fetchData(page, pageSize || 20, searchTerm);
  };

  const handleContentClick = (content: string) => {
    showDrawer(content);
  };

  return (
    <div className="w-full h-full">
      <div className="flex justify-end items-center mb-4">
        <Input.Search
          placeholder={`${t('common.search')}...`}
          allowClear
          enterButton
          size="middle"
          onSearch={handleSearch}
          style={{ width: '240px' }}
        />
      </div>
      {loading ? (
        <div className="flex justify-center items-center w-full h-full">
          <Spin size="large" />
        </div>
      ) : (
        <>
          <div className={`${styles.resultWrap}`}>
            <div className='grid grid-cols-4 gap-4'>
              {paragraphsState.map((paragraph, index) => (
                <div key={paragraph.id} className="p-2 cursor-pointer" onClick={() => handleContentClick(paragraph.content)}>
                  <Card
                    size="small"
                    className={`rounded-lg flex flex-col justify-between ${styles.resultCard}`}
                    title={
                      <div className="flex justify-between items-center">
                        <span className={`text-xs ${styles.number}`}>
                          #{index.toString().padStart(3, '0')}
                        </span>
                      </div>
                    }
                  >
                    <p className={`${styles.truncateLines}`}>
                      {paragraph.content || '--'}
                    </p>
                  </Card>
                </div>
              ))}
            </div>
          </div>
          <div className="flex justify-end mt-4">
            <Pagination
              current={currentPage}
              pageSize={pageSize}
              total={totalItems}
              onChange={handlePageChange}
              showSizeChanger
              pageSizeOptions={['10', '20', '50', '100']}
            />
          </div>
        </>
      )}
      <ContentDrawer
        visible={drawerVisible}
        onClose={hideDrawer}
        content={drawerContent}
      />
    </div>
  );
};

export default DocsResultPage;
