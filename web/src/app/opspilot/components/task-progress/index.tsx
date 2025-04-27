import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import styles from './index.module.scss';
import { useTranslation } from '@/utils/i18n';

interface Task {
  id: number;
  name: string;
  train_progress: number;
}

const TaskProgress: React.FC = () => {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<Task[]>([]);
  const { fetchDocuments } = useKnowledgeApi();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;

  useEffect(() => {
    const params = {
      train_status: 0,
      knowledge_base_id: id
    };
    const fetchTasks = async () => {
      try {
        const data = await fetchDocuments(params);
        setTasks(data);
      } catch (error) {
        console.error(`${t('common.fetchFailed')}: ${error}`);
      }
    };

    fetchTasks();
    const interval = setInterval(fetchTasks, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-4 absolute bottom-10 left-0 w-full max-h-[300px] overflow-y-auto">
      {tasks.map((task) => (
        <div key={task.id} className="mb-2">
          <div className="flex justify-between items-center text-xs mb-1">
            <span>{task.name}</span>
            <span>{task.train_progress}%</span>
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
