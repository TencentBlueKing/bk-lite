import { useState, useEffect } from 'react';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { groupProps } from '@/types/index';

const useGroups = () => {
  const { t } = useTranslation();
  const { get, isLoading } = useApiClient();
  const [groups, setGroups] = useState<groupProps[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    if (isLoading) return;
    const fetchGroups = async () => {
      try {
        const data = await get('/opspilot/knowledge_mgmt/knowledge_base/get_teams/');
        setGroups(data || []);
      } catch (error) {
        console.error(`${t('common.fetchFailed')}:`, error);
      } finally {
        setLoading(false);
      }
    };
    fetchGroups();
  }, [get, isLoading]);

  return { groups, loading };
};

export default useGroups;
