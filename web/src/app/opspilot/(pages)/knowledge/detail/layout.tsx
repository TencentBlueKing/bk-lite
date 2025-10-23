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
  const id = searchParams?.get('id') || '';
  const name = searchParams?.get('name') || '';
  const desc = searchParams?.get('desc') || '';
  
  // Get current tab state from Context
  const { mainTabKey } = useDocuments();

  const handleBackButtonClick = () => {
    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    if (pathSegments.length >= 3) {
      if (pathSegments.length === 3) {
        router.push('/knowledge');
      } else if (pathSegments.length > 3) {
        router.push(`/opspilot/knowledge/detail?id=${id}&name=${name}&desc=${desc}`);
      }
    }
    else {
      router.back();
    }
  };

  const intro = (
    <OnelineEllipsisIntro name={name} desc={desc}></OnelineEllipsisIntro>
  );

  // Determine whether to show TaskProgress based on current page and tab state
  const shouldShowTaskProgress = () => {
    if (pathname === '/opspilot/knowledge/detail/documents') {
      // Only show in source_files and qa_pairs main tabs
      return mainTabKey === 'source_files' || mainTabKey === 'qa_pairs';
    }
    
    if (pathname === '/opspilot/knowledge/detail/documents/result') {
      // Show TaskProgress for document result pages
      return true;
    }
    
    return false;
  };

  // Determine the activeTabKey to pass to TaskProgress based on current state
  const getTaskProgressActiveKey = (): string | undefined => {
    // For result pages, we don't need activeTabKey since pageType handles the logic
    if (pathname === '/opspilot/knowledge/detail/documents/result') {
      return undefined;
    }
    
    if (mainTabKey === 'qa_pairs') return 'qa_pairs';
    if (mainTabKey === 'source_files') return 'source_files';
    return undefined;
  };

  // Determine the page type for TaskProgress
  const getTaskProgressPageType = (): 'documents' | 'result' => {
    if (pathname === '/opspilot/knowledge/detail/documents/result') {
      return 'result';
    }
    return 'documents';
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
