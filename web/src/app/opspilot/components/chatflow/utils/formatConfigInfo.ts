import type { ChatflowNodeData, CeleryNodeConfig, HttpNodeConfig, AgentsNodeConfig, ConditionNodeConfig, IntentClassificationNodeConfig, EnterpriseWechatNodeConfig, DingtalkNodeConfig, WechatOfficialNodeConfig, NotificationNodeConfig, WebChatNodeConfig, MobileNodeConfig } from '../types';

export const formatConfigInfo = (data: ChatflowNodeData, t: any) => {
  const config = data.config;

  if (!config || Object.keys(config).length === 0) {
    return t('chatflow.notConfigured');
  }

  switch (data.type) {
    case 'celery': {
      const celeryConfig = config as CeleryNodeConfig;
      if (celeryConfig.frequency) {
        const frequencyMap: { [key: string]: string } = {
          'daily': t('chatflow.daily'),
          'weekly': t('chatflow.weekly'),
          'monthly': t('chatflow.monthly')
        };
        const timeStr = celeryConfig.time ? ` ${typeof celeryConfig.time === 'object' && celeryConfig.time.format ? celeryConfig.time.format('HH:mm') : celeryConfig.time}` : '';
        const weekdayStr = celeryConfig.weekday !== undefined ? ` ${t('chatflow.weekday')}${celeryConfig.weekday}` : '';
        const dayStr = celeryConfig.day ? ` ${celeryConfig.day}${t('chatflow.day')}` : '';
        return `${frequencyMap[celeryConfig.frequency] || celeryConfig.frequency}${timeStr}${weekdayStr}${dayStr}`;
      }
      return t('chatflow.triggerFrequency') + ': --';
    }

    case 'http': {
      const httpConfig = config as HttpNodeConfig;
      if (httpConfig.method && httpConfig.url) {
        return `${httpConfig.method} ${httpConfig.url}`;
      } else if (httpConfig.method) {
        return httpConfig.method;
      } else if (httpConfig.url) {
        return httpConfig.url;
      }
      return t('chatflow.httpMethod') + ': --';
    }

    case 'agents': {
      const agentsConfig = config as AgentsNodeConfig;
      if (agentsConfig.agent) {
        const agentDisplayName = agentsConfig.agentName || agentsConfig.agent;
        return t('chatflow.selectedAgent') + `: ${agentDisplayName}`;
      }
      return t('chatflow.selectedAgent') + ': --';
    }

    case 'condition': {
      const conditionConfig = config as ConditionNodeConfig;
      if (conditionConfig.conditionField && conditionConfig.conditionOperator && conditionConfig.conditionValue) {
        return `${conditionConfig.conditionField} ${conditionConfig.conditionOperator} ${conditionConfig.conditionValue}`;
      }
      return t('chatflow.condition') + ': --';
    }

    case 'restful':
    case 'openai':
      return t('chatflow.apiInterface');

    case 'notification': {
      const notificationConfig = config as NotificationNodeConfig;
      if (notificationConfig.notificationType && notificationConfig.notificationMethod && notificationConfig.notificationChannels) {
        const selectedChannel = notificationConfig.notificationChannels.find((channel: { id: string; name: string }) =>
          channel.id === notificationConfig.notificationMethod
        );
        const channelName = selectedChannel ? selectedChannel.name : `ID: ${notificationConfig.notificationMethod}`;
        const typeDisplay = notificationConfig.notificationType === 'email' ? t('chatflow.email') : t('chatflow.enterpriseWechatBot');
        return `${typeDisplay} - ${channelName}`;
      } else if (notificationConfig.notificationType) {
        const typeDisplay = notificationConfig.notificationType === 'email' ? t('chatflow.email') : t('chatflow.enterpriseWechatBot');
        return `${typeDisplay} - ${t('chatflow.notificationMethod')}: --`;
      }
      return t('chatflow.notificationCategory') + ': --';
    }

    case 'enterprise_wechat': {
      const wechatConfig = config as EnterpriseWechatNodeConfig;
      if (wechatConfig.token && wechatConfig.corp_id && wechatConfig.agent_id) {
        const configuredParams = [];
        if (wechatConfig.token) configuredParams.push('Token');
        if (wechatConfig.secret) configuredParams.push('Secret');
        if (wechatConfig.aes_key) configuredParams.push('AES Key');
        if (wechatConfig.corp_id) configuredParams.push('Corp ID');
        if (wechatConfig.agent_id) configuredParams.push('Agent ID');
        return `已配置: ${configuredParams.join(', ')}`;
      }
      return t('chatflow.notConfigured');
    }

    case 'dingtalk': {
      const dingtalkConfig = config as DingtalkNodeConfig;
      if (dingtalkConfig.client_id && dingtalkConfig.client_secret) {
        return `已配置: Client ID, Client Secret`;
      }
      return t('chatflow.notConfigured');
    }

    case 'wechat_official': {
      const officialConfig = config as WechatOfficialNodeConfig;
      if (officialConfig.token && officialConfig.appid) {
        const configuredParams = [];
        if (officialConfig.token) configuredParams.push('Token');
        if (officialConfig.appid) configuredParams.push('AppID');
        if (officialConfig.secret) configuredParams.push('Secret');
        if (officialConfig.aes_key) configuredParams.push('AES Key');
        return `已配置: ${configuredParams.join(', ')}`;
      }
      return t('chatflow.notConfigured');
    }

    case 'web_chat': {
      const webChatConfig = config as WebChatNodeConfig;
      if (webChatConfig.appName) {
        return webChatConfig.appName;
      }
      return t('chatflow.notConfigured');
    }

    case 'mobile': {
      const mobileConfig = config as MobileNodeConfig;
      if (mobileConfig.appName) {
        const tags = mobileConfig.appTags && mobileConfig.appTags.length > 0 
          ? ` (${mobileConfig.appTags.length}个标签)` 
          : '';
        return `${mobileConfig.appName}${tags}`;
      }
      return t('chatflow.notConfigured');
    }

    case 'agui':
    case 'embedded_chat':
      return t('chatflow.apiInterface');

    case 'intent_classification': {
      const intentConfig = config as IntentClassificationNodeConfig;
      if (intentConfig.intents && intentConfig.intents.length > 0) {
        const intentNames = intentConfig.intents.map((intent: { name: string }) => intent.name).join(', ');
        return `${t('chatflow.intentClassification')}: ${intentNames}`;
      }
      return t('chatflow.notConfigured');
    }

    default:
      return t('chatflow.notConfigured');
  }
};