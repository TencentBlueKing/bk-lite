import type { ChatflowNodeData } from '../types';

export const formatConfigInfo = (data: ChatflowNodeData, t: any) => {
  const config = data.config;

  if (!config || Object.keys(config).length === 0) {
    return t('chatflow.notConfigured');
  }

  switch (data.type) {
    case 'celery':
      if (config.frequency) {
        const frequencyMap: { [key: string]: string } = {
          'daily': t('chatflow.daily'),
          'weekly': t('chatflow.weekly'),
          'monthly': t('chatflow.monthly')
        };
        const timeStr = config.time ? ` ${config.time.format ? config.time.format('HH:mm') : config.time}` : '';
        const weekdayStr = config.weekday !== undefined ? ` ${t('chatflow.weekday')}${config.weekday}` : '';
        const dayStr = config.day ? ` ${config.day}${t('chatflow.day')}` : '';
        return `${frequencyMap[config.frequency] || config.frequency}${timeStr}${weekdayStr}${dayStr}`;
      }
      return t('chatflow.triggerFrequency') + ': --';

    case 'http':
      if (config.method && config.url) {
        return `${config.method} ${config.url}`;
      } else if (config.method) {
        return config.method;
      } else if (config.url) {
        return config.url;
      }
      return t('chatflow.httpMethod') + ': --';

    case 'agents':
      if (config.agent) {
        const agentDisplayName = config.agentName || config.agent;
        return t('chatflow.selectedAgent') + `: ${agentDisplayName}`;
      }
      return t('chatflow.selectedAgent') + ': --';

    case 'condition':
      if (config.conditionField && config.conditionOperator && config.conditionValue) {
        return `${config.conditionField} ${config.conditionOperator} ${config.conditionValue}`;
      }
      return t('chatflow.condition') + ': --';

    case 'restful':
    case 'openai':
      return t('chatflow.apiInterface');

    case 'notification':
      if (config.notificationType && config.notificationMethod && config.notificationChannels) {
        const selectedChannel = config.notificationChannels.find((channel: any) =>
          channel.id === config.notificationMethod
        );
        const channelName = selectedChannel ? selectedChannel.name : `ID: ${config.notificationMethod}`;
        const typeDisplay = config.notificationType === 'email' ? t('chatflow.email') : t('chatflow.enterpriseWechatBot');
        return `${typeDisplay} - ${channelName}`;
      } else if (config.notificationType) {
        const typeDisplay = config.notificationType === 'email' ? t('chatflow.email') : t('chatflow.enterpriseWechatBot');
        return `${typeDisplay} - ${t('chatflow.notificationMethod')}: --`;
      }
      return t('chatflow.notificationCategory') + ': --';

    case 'enterprise_wechat':
      if (config.token && config.corp_id && config.agent_id) {
        const configuredParams = [];
        if (config.token) configuredParams.push('Token');
        if (config.secret) configuredParams.push('Secret');
        if (config.aes_key) configuredParams.push('AES Key');
        if (config.corp_id) configuredParams.push('Corp ID');
        if (config.agent_id) configuredParams.push('Agent ID');
        return `已配置: ${configuredParams.join(', ')}`;
      }
      return t('chatflow.notConfigured');

    case 'dingtalk':
      if (config.client_id && config.client_secret) {
        return `已配置: Client ID, Client Secret`;
      }
      return t('chatflow.notConfigured');

    case 'wechat_official':
      if (config.token && config.appid) {
        const configuredParams = [];
        if (config.token) configuredParams.push('Token');
        if (config.appid) configuredParams.push('AppID');
        if (config.secret) configuredParams.push('Secret');
        if (config.aes_key) configuredParams.push('AES Key');
        return `已配置: ${configuredParams.join(', ')}`;
      }
      return t('chatflow.notConfigured');

    case 'web_chat':
      if (config.appName) {
        return config.appName;
      }
      return t('chatflow.notConfigured');

    case 'mobile':
      if (config.appName) {
        const tags = config.appTags && config.appTags.length > 0 
          ? ` (${config.appTags.length}个标签)` 
          : '';
        return `${config.appName}${tags}`;
      }
      return t('chatflow.notConfigured');

    case 'agui':
    case 'embedded_chat':
      return t('chatflow.apiInterface');

    default:
      return t('chatflow.notConfigured');
  }
};
