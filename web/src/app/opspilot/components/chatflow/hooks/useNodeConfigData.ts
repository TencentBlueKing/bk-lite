import { useState, useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { useChannelApi } from '@/app/system-manager/api/channel';
import { useStudioApi } from '@/app/opspilot/api/studio';

export const useNodeConfigData = () => {
  const { t } = useTranslation();
  const { fetchSkill } = useSkillApi();
  const { getChannelData } = useChannelApi();
  const { getAllUsers } = useStudioApi();

  const [skills, setSkills] = useState<any[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [notificationChannels, setNotificationChannels] = useState<any[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersLoaded, setUsersLoaded] = useState(false);

  const loadSkills = useCallback(async () => {
    try {
      setLoadingSkills(true);
      const data = await fetchSkill({ is_template: 0 });
      setSkills(data || []);
    } catch (error) {
      console.error('Failed to load skills:', error);
      message.error(t('skill.settings.noSkillHasBeenSelected'));
    } finally {
      setLoadingSkills(false);
    }
  }, [fetchSkill, t]);

  const loadChannels = useCallback(async (channelType: 'email' | 'enterprise_wechat_bot') => {
    try {
      setLoadingChannels(true);
      const data = await getChannelData({ channel_type: channelType });
      setNotificationChannels(data);
    } catch (error) {
      console.error('Failed to load channels:', error);
      message.error(t('chatflow.fetchNotificationChannelsFailed'));
      setNotificationChannels([]);
    } finally {
      setLoadingChannels(false);
    }
  }, [getChannelData, t]);

  const loadUsers = useCallback(async () => {
    if (usersLoaded) return;
    try {
      setLoadingUsers(true);
      const data = await getAllUsers();
      setAllUsers(data || []);
      setUsersLoaded(true);
    } catch (error) {
      console.error('Failed to load users:', error);
      message.error(t('chatflow.fetchUsersFailed'));
      setAllUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  }, [getAllUsers, usersLoaded, t]);

  return {
    skills,
    loadingSkills,
    loadSkills,
    notificationChannels,
    loadingChannels,
    loadChannels,
    allUsers,
    loadingUsers,
    loadUsers,
  };
};
