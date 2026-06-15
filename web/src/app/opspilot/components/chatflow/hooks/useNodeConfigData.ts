import { useState, useCallback } from 'react';
import { message } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSkillApi } from '@/app/opspilot/api/skill';
import { useChannelApi } from '@/app/system-manager/api/channel';
import { useStudioApi } from '@/app/opspilot/api/studio';
import { useMemoryApi, type WorkflowMemorySpaceOption } from '@/app/opspilot/api/memory';
import type { LlmModel } from '@/app/opspilot/types/skill';

export const useNodeConfigData = () => {
  const { t } = useTranslation();
  const { fetchSkill, fetchLlmModels } = useSkillApi();
  const { getChannelData } = useChannelApi();
  const { getAllUsers } = useStudioApi();
  const { fetchWorkflowMemorySpaces } = useMemoryApi();

  const [skills, setSkills] = useState<any[]>([]);
  const [loadingSkills, setLoadingSkills] = useState(false);
  const [skillsLoaded, setSkillsLoaded] = useState(false);
  const [llmModels, setLlmModels] = useState<LlmModel[]>([]);
  const [loadingLlmModels, setLoadingLlmModels] = useState(false);
  const [llmModelsLoaded, setLlmModelsLoaded] = useState(false);
  const [notificationChannels, setNotificationChannels] = useState<any[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersLoaded, setUsersLoaded] = useState(false);
  const [memorySpaces, setMemorySpaces] = useState<WorkflowMemorySpaceOption[]>([]);
  const [loadingMemorySpaces, setLoadingMemorySpaces] = useState(false);
  const [memorySpacesLoaded, setMemorySpacesLoaded] = useState(false);

  const loadSkills = useCallback(async () => {
    if (skillsLoaded) return;
    try {
      setLoadingSkills(true);
      const data = await fetchSkill({ is_template: 0 });
      // 处理两种返回格式：分页格式 { count, items } 或直接返回列表
      const items = Array.isArray(data) ? data : (data?.items || []);
      setSkills(items);
      setSkillsLoaded(true);
    } catch (error) {
      console.error('Failed to load skills:', error);
      message.error(t('skill.settings.noSkillHasBeenSelected'));
    } finally {
      setLoadingSkills(false);
    }
  }, [fetchSkill, skillsLoaded, t]);

  const loadLlmModels = useCallback(async () => {
    if (llmModelsLoaded) return;
    try {
      setLoadingLlmModels(true);
      const data = await fetchLlmModels();
      setLlmModels(data || []);
      setLlmModelsLoaded(true);
    } catch (error) {
      console.error('Failed to load llm models:', error);
      message.error(t('chatflow.fetchLlmModelsFailed'));
      setLlmModels([]);
    } finally {
      setLoadingLlmModels(false);
    }
  }, [fetchLlmModels, llmModelsLoaded, t]);

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

  const loadMemorySpaces = useCallback(async () => {
    if (memorySpacesLoaded) return;
    try {
      setLoadingMemorySpaces(true);
      const data = await fetchWorkflowMemorySpaces();
      setMemorySpaces(data || []);
      setMemorySpacesLoaded(true);
    } catch (error) {
      console.error('Failed to load memory spaces:', error);
      message.error(t('chatflow.fetchMemorySpacesFailed'));
      setMemorySpaces([]);
    } finally {
      setLoadingMemorySpaces(false);
    }
  }, [fetchWorkflowMemorySpaces, memorySpacesLoaded, t]);

  return {
    skills,
    loadingSkills,
    loadSkills,
    llmModels,
    loadingLlmModels,
    loadLlmModels,
    notificationChannels,
    loadingChannels,
    loadChannels,
    allUsers,
    loadingUsers,
    loadUsers,
    memorySpaces,
    loadingMemorySpaces,
    loadMemorySpaces,
  };
};
