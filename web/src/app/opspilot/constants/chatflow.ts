export const nodeConfig = {
  celery: { icon: 'a-icon-dingshichufa1x', color: 'green' as const },
  restful: { icon: 'RESTfulAPI', color: 'purple' as const },
  openai: { icon: 'icon-test2', color: 'blue' as const },
  agents: { icon: 'zhinengti', color: 'orange' as const },
  condition: { icon: 'tiaojianfenzhi', color: 'yellow' as const },
  http: { icon: 'HTTP', color: 'cyan' as const },
  notification: { icon: 'alarm', color: 'pink' as const },
  enterprise_wechat: { icon: 'qiwei2', color: 'green' as const },
  dingtalk: { icon: 'dingding', color: 'blue' as const },
  wechat_official: { icon: 'weixingongzhonghao', color: 'green' as const },
} as const;

export const TRIGGER_NODE_TYPES = ['celery', 'restful', 'openai', 'enterprise_wechat', 'dingtalk', 'wechat_official'] as const;

export const handleColorClasses = {
  green: '!bg-green-500',
  purple: '!bg-purple-500',
  blue: '!bg-blue-500',
  orange: '!bg-orange-500',
  yellow: '!bg-yellow-500',
  cyan: '!bg-cyan-500',
  pink: '!bg-pink-500',
} as const;

export const getDefaultConfig = (nodeType: string) => {
  const baseConfig = {
    inputParams: 'last_message',
    outputParams: 'last_message'
  };

  switch (nodeType) {
    case 'celery':
      return {
        ...baseConfig,
        frequency: 'daily',
        time: null,
        message: ''
      };
    case 'http':
      return {
        ...baseConfig,
        method: 'GET',
        url: '',
        params: [],
        headers: [],
        requestBody: '',
        timeout: 30,
        outputMode: 'once'
      };
    case 'agents':
      return {
        ...baseConfig,
        agent: null,
        agentName: '',
        prompt: '',
        uploadedFiles: []
      };
    case 'condition':
      return {
        ...baseConfig,
        conditionField: '',
        conditionOperator: 'equals',
        conditionValue: ''
      };
    case 'enterprise_wechat':
      return {
        ...baseConfig,
        token: '',
        secret: '',
        aes_key: '',
        corp_id: '',
        agent_id: ''
      };
    case 'restful':
    case 'openai':
      return baseConfig;
    default:
      return baseConfig;
  }
};
