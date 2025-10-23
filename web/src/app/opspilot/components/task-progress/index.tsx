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
  pageType?: 'documents' | 'result';
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
    const fetchTasks = async () => {
      try {
        if (pageType === 'result' && documentId) {
          // For result page, use the new API with documentId
          const data: QATaskStatus[] = await fetchQAPairsTaskStatus({ document_id: documentId });
          setQaTaskStatuses(data);
          setTasks([]); // Clear regular tasks
        } else if (pageType === 'documents' && id) {
          // For documents page, use the existing API with knowledge_base_id
          const params = {
            knowledge_base_id: id
          };
          const data: Task[] = await fetchMyTasks(params);
          setTasks(data);
          setQaTaskStatuses([]); // Clear QA task statuses
        }
      } catch (error) {
        console.error(`${t('common.fetchFailed')}: ${error}`);
      }
    };

    fetchTasks();
    const interval = setInterval(fetchTasks, 10000);
    return () => clearInterval(interval);
  }, [pageType, id, documentId]);

  // Filter tasks based on activeTabKey and pageType
  const filteredTasks = tasks.filter((task) => {
    // For result page, tasks are handled separately
    if (pageType === 'result') {
      return false;
    }

    // For documents page, use existing logic
    if (!activeTabKey || (activeTabKey !== 'source_files' && activeTabKey !== 'qa_pairs')) {
      return false;
    }

    // For source_files tab, show tasks where is_qa_task is false
    if (activeTabKey === 'source_files') {
      return !task.is_qa_task;
    }

    // For qa_pairs tab, show tasks where is_qa_task is true
    if (activeTabKey === 'qa_pairs') {
      return task.is_qa_task;
    }

    return false;
  });

  // For result page, show QA task statuses if available
  const shouldShowQAStatuses = pageType === 'result' && qaTaskStatuses.length > 0;
  
  // Don't render if no filtered tasks and no QA statuses
  if (filteredTasks.length === 0 && !shouldShowQAStatuses) {
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
      
      {/* Render regular tasks for documents page */}
      {filteredTasks.map((task) => (
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
