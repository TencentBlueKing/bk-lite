export const nodeConfig = {
  celery: { icon: 'a-icon-dingshichufa1x', color: 'green' as const },
  nats: { icon: 'WebSphereMQ', color: 'cyan' as const },
  restful: { icon: 'RESTfulAPI', color: 'purple' as const },
  openai: { icon: 'icon-test2', color: 'blue' as const },
  agents: { icon: 'zhinengti', color: 'orange' as const },
  agui: { icon: 'zhinengti', color: 'teal' as const },
  embedded_chat: { icon: 'wendaduihua', color: 'purple' as const },
  web_chat: { icon: 'WebSphereMQ', color: 'cyan' as const },
  mobile: { icon: 'zhuji', color: 'indigo' as const },
  condition: { icon: 'tiaojianfenzhi', color: 'yellow' as const },
  intent_classification: { icon: 'question-circle-fill', color: 'purple' as const },
  http: { icon: 'HTTP', color: 'cyan' as const },
  notification: { icon: 'alarm', color: 'pink' as const },
  enterprise_wechat: { icon: 'qiwei2', color: 'green' as const },
  enterprise_wechat_aibot: { icon: 'qiwei2', color: 'green' as const },
  dingtalk: { icon: 'dingding', color: 'blue' as const },
  wechat_official: { icon: 'weixingongzhonghao', color: 'green' as const },
  memory_read: { icon: 'zhishiku2', color: 'teal' as const },
  memory_write: { icon: 'bianji', color: 'indigo' as const },
} as const;

export const TRIGGER_NODE_TYPES = ['celery', 'nats', 'restful', 'openai', 'agui', 'embedded_chat', 'web_chat', 'mobile', 'enterprise_wechat', 'enterprise_wechat_aibot', 'dingtalk', 'wechat_official'] as const;

export const nodeCategories = [
  {
    key: 'triggers',
    labelKey: 'chatflow.triggers',
    items: [
      { type: 'celery', icon: 'a-icon-dingshichufa1x', labelKey: 'chatflow.celery' },
      { type: 'nats', icon: 'WebSphereMQ', labelKey: 'chatflow.nats' },
      { type: 'restful', icon: 'RESTfulAPI', labelKey: 'chatflow.restful' },
      { type: 'openai', icon: 'icon-test2', labelKey: 'chatflow.openai' },
      { type: 'agui', icon: 'huifu-copy', labelKey: 'chatflow.agui' },
    ],
  },
  {
    key: 'applications',
    labelKey: 'chatflow.applications',
    items: [
      { type: 'embedded_chat', icon: 'wendaduihua', labelKey: 'chatflow.embeddedChat' },
      { type: 'web_chat', icon: 'WebSphereMQ', labelKey: 'chatflow.webChat' },
      { type: 'mobile', icon: 'zhuji', labelKey: 'chatflow.mobile' },
      { type: 'enterprise_wechat', icon: 'qiwei2', labelKey: 'chatflow.enterpriseWechat' },
      { type: 'enterprise_wechat_aibot', icon: 'qiwei2', labelKey: 'chatflow.enterpriseWechatAibot' },
      { type: 'dingtalk', icon: 'dingding', labelKey: 'chatflow.dingtalk' },
      { type: 'wechat_official', icon: 'weixingongzhonghao', labelKey: 'chatflow.wechatOfficial' },
    ],
  },
  {
    key: 'agents',
    labelKey: 'chatflow.agents',
    items: [
      { type: 'agents', icon: 'zhinengti', labelKey: 'chatflow.agents' },
    ],
  },
  {
    key: 'logic',
    labelKey: 'chatflow.logicNodes',
    items: [
      { type: 'condition', icon: 'tiaojianfenzhi', labelKey: 'chatflow.condition' },
      { type: 'intent_classification', icon: 'question-circle-fill', labelKey: 'chatflow.intentClassification' },
    ],
  },
  {
    key: 'memory',
    labelKey: 'chatflow.memoryNodes',
    items: [
      { type: 'memory_read', icon: 'zhishiku2', labelKey: 'chatflow.memoryRead' },
      { type: 'memory_write', icon: 'bianji', labelKey: 'chatflow.memoryWrite' },
    ],
  },
  {
    key: 'actions',
    labelKey: 'chatflow.actionNodes',
    items: [
      { type: 'http', icon: 'HTTP', labelKey: 'chatflow.http' },
      { type: 'notification', icon: 'alarm', labelKey: 'chatflow.notification' },
    ],
  },
] as const;

export const handleColorClasses = {
  green: 'bg-green-500!',
  purple: 'bg-purple-500!',
  blue: 'bg-blue-500!',
  orange: 'bg-orange-500!',
  teal: 'bg-teal-500!',
  indigo: 'bg-indigo-500!',
  yellow: 'bg-yellow-500!',
  cyan: 'bg-cyan-500!',
  pink: 'bg-pink-500!',
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
        time: '00:00',
        message: ''
      };
    case 'nats':
      return baseConfig;
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
    case 'notification':
      return {
        ...baseConfig,
        notificationType: 'email',
        notificationMethod: '',
        notificationChannels: []
      };
    case 'agui':
      return {
        name: 'AG-UI',
        inputParams: 'last_message',
        outputParams: 'last_message'
      };
    case 'embedded_chat':
      return {
        name: '嵌入式对话',
        inputParams: 'last_message',
        outputParams: 'last_message'
      };
    case 'condition':
      return {
        ...baseConfig,
        conditionField: '',
        conditionOperator: 'equals',
        conditionValue: ''
      };
    case 'intent_classification':
      return {
        ...baseConfig,
        llmModel: null,
        llmModelName: '',
        classificationRules: '',
        intents: [
          { name: '默认意图' }
        ]
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
    case 'enterprise_wechat_aibot':
      return {
        ...baseConfig,
        connectionMode: 'webhook',
        webhook: {
          token: '',
          encodingAESKey: '',
          aibotid: ''
        },
        websocket: {
          botId: '',
          secret: ''
        }
      };
    case 'web_chat':
      return {
        ...baseConfig,
        appName: '',
        appDescription: ''
      };
    case 'mobile':
      return {
        ...baseConfig,
        appName: '',
        appTags: [],
        appDescription: ''
      };
    case 'memory_read':
      return {
        ...baseConfig,
        memory_space_id: null,
        top_k: 5
      };
    case 'memory_write':
      return {
        ...baseConfig,
        memory_space_id: null,
        title: '',
        writeBatchSize: 30
      };
    case 'restful':
    case 'openai':
    default:
      return baseConfig;
  }
};
