'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import TaskProgress from '@/app/opspilot/components/task-progress'
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { DocumentsProvider, useDocuments } from '@/app/opspilot/context/documentsContext';

interface KnowledgeDetailLayoutProps {
  children: React.ReactNode;
}

const LayoutContent: React.FC<KnowledgeDetailLayoutProps> = ({ children }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const name = searchParams?.get('name') || '';
  const desc = searchParams?.get('desc') || '';
  
  const { mainTabKey } = useDocuments();

  const handleBackButtonClick = () => {
    router.push('/opspilot/knowledge');
  };

  const intro = (
    <OnelineEllipsisIntro name={name} desc={desc}></OnelineEllipsisIntro>
  );

  // Show TaskProgress on documents page (source_files/qa_pairs/knowledge_graph tabs), result pages
  const shouldShowTaskProgress = () => {
    if (pathname === '/opspilot/knowledge/detail/documents') {
      return mainTabKey === 'source_files' || mainTabKey === 'qa_pairs' || mainTabKey === 'knowledge_graph';
    }
    
    if (pathname === '/opspilot/knowledge/detail/documents/result') {
      return true;
    }
    
    return false;
  };

  const getTaskProgressActiveKey = (): string | undefined => {
    if (pathname === '/opspilot/knowledge/detail/documents/result') {
      return undefined;
    }
    
    if (mainTabKey === 'knowledge_graph') return 'knowledge_graph';
    if (mainTabKey === 'qa_pairs') return 'qa_pairs';
    if (mainTabKey === 'source_files') return 'source_files';
    return undefined;
  };

  const getTaskProgressPageType = (): 'documents' | 'qa_pairs' | 'knowledge_graph' | 'result' => {
    if (pathname === '/opspilot/knowledge/detail/documents/result') {
      return 'result';
    }
    return (mainTabKey as 'documents' | 'qa_pairs' | 'knowledge_graph') || 'documents';
  };

  const getTopSectionContent = () => {
    switch (pathname) {
      case '/opspilot/knowledge/detail/documents':
        return (
          <TopSection
            title={t('knowledge.documents.title')}
            content={t('knowledge.documents.description')}
          />
        );
      case '/opspilot/knowledge/detail/testing':
        return (
          <TopSection
            title={t('knowledge.testing.title')}
            content={t('knowledge.testing.description')}
          />
        );
      case '/opspilot/knowledge/detail/settings':
        return (
          <TopSection
            title={t('knowledge.settings.title')}
            content={t('knowledge.testing.description')}
          />
        );
      default:
        return (
          <TopSection
            title={t('knowledge.documents.title')}
            content={t('knowledge.documents.description')}
          />
        );
    }
  };

  const topSection = getTopSectionContent();
  const taskProgressActiveKey = getTaskProgressActiveKey();
  const taskProgressPageType = getTaskProgressPageType();

  return (
    <WithSideMenuLayout
      topSection={topSection}
      intro={intro}
      showBackButton={true}
      showProgress={shouldShowTaskProgress()}
      taskProgressComponent={
        shouldShowTaskProgress() ? (
          <TaskProgress 
            activeTabKey={taskProgressActiveKey}
            pageType={taskProgressPageType}
          />
        ) : null
      }
      onBackButtonClick={handleBackButtonClick}
    >
      {children}
    </WithSideMenuLayout>
  );
};

const KnowledgeDetailLayout: React.FC<KnowledgeDetailLayoutProps> = ({ children }) => {
  return (
    <DocumentsProvider>
      <LayoutContent>
        {children}
      </LayoutContent>
    </DocumentsProvider>
  );
};

export default KnowledgeDetailLayout;
