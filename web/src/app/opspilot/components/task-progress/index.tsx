import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';

interface Task {
  id: number;
  task_name: string;
  train_progress: number;
  is_qa_task: boolean;
}

interface QATaskStatus {
  process: string;
  status: string;
}

interface TaskProgressProps {
  activeTabKey?: string;
  pageType?: 'documents' | 'qa_pairs' | 'knowledge_graph' | 'result';
}

const TaskProgress: React.FC<TaskProgressProps> = ({ activeTabKey, pageType = 'documents' }) => {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [qaTaskStatuses, setQaTaskStatuses] = useState<QATaskStatus[]>([]);
  const { fetchMyTasks, fetchQAPairsTaskStatus } = useKnowledgeApi();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const documentId = searchParams ? searchParams.get('documentId') : null;

  useEffect(() => {
    // Clear tasks immediately when tab changes
    setTasks([]);
    setQaTaskStatuses([]);

    // Use flag to prevent stale data updates
    let isCurrentRequest = true;

    const fetchTasks = async () => {
      try {
        // For result page, use fetchQAPairsTaskStatus API with documentId
        if (pageType === 'result' && documentId) {
          const data: QATaskStatus[] = await fetchQAPairsTaskStatus({ document_id: documentId });
          if (isCurrentRequest) {
            setQaTaskStatuses(data);
            setTasks([]); // Clear regular tasks
          }
          return;
        }

        // For documents/qa_pairs/knowledge_graph pages, use fetchMyTasks with knowledge_base_id
        if (!id) return;

        const params: any = {
          knowledge_base_id: id
        };

        // Add parameters based on pageType
        if (pageType === 'qa_pairs') {
          params.is_qa_task = 1;
        } else if (pageType === 'knowledge_graph') {
          params.is_graph = 1;
        }
        // For documents (source_files), only pass knowledge_base_id

        const data: Task[] = await fetchMyTasks(params);
        
        // Only update state if this is still the current request
        if (isCurrentRequest) {
          setTasks(data);
          setQaTaskStatuses([]); // Clear QA task statuses
        }
      } catch (error) {
        if (isCurrentRequest) {
          console.error(`${t('common.fetchFailed')}: ${error}`);
        }
      }
    };

    fetchTasks();
    const interval = setInterval(fetchTasks, 10000);
    
    return () => {
      isCurrentRequest = false;
      clearInterval(interval);
    };
  }, [pageType, id, documentId, activeTabKey]);

  // For result page, show QA task statuses if available
  const shouldShowQAStatuses = pageType === 'result' && qaTaskStatuses.length > 0;
  
  // Don't render if no tasks and no QA statuses
  if (tasks.length === 0 && !shouldShowQAStatuses) {
    return null;
  }

  return (
    <div className="p-4 absolute bottom-10 left-0 w-full max-h-[300px] overflow-y-auto">
      {/* Render QA task statuses for result page */}
      {shouldShowQAStatuses && qaTaskStatuses.map((qaStatus, index) => (
        <div key={`qa-${index}`} className="mb-2">
          <div className="flex justify-between items-center text-xs mb-1">
            <span className="flex-1 truncate" title={qaStatus.status}>
              {qaStatus.status}
            </span>
            <span className="ml-2 flex-shrink-0">{qaStatus.process}</span>
          </div>
          <div className={`w-full h-2 rounded relative overflow-hidden ${styles.progressContainer}`}>
            <div className={`${styles.progressBar} h-full w-full`}></div>
          </div>
        </div>
      ))}
      
      {/* Render regular tasks for other pages */}
      {tasks.map((task) => (
        <div key={task.id} className="mb-2">
          <div className="flex justify-between items-center text-xs mb-1">
            <span className="flex-1 truncate" title={task.task_name}>
              {task.task_name}
            </span>
            <span className="ml-2 flex-shrink-0">{task.train_progress}</span>
          </div>
          <div className={`w-full h-2 rounded relative overflow-hidden ${styles.progressContainer}`}>
            <div className={`${styles.progressBar} h-full w-full`}></div>
          </div>
        </div>
      ))}
    </div>
  );
};

export default TaskProgress;
