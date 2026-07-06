import { getDefaultConfig, nodeCategories, nodeConfig, TRIGGER_NODE_TYPES } from '../src/app/opspilot/constants/chatflow';
import { formatConfigInfo } from '../src/app/opspilot/components/chatflow/utils/formatConfigInfo';

function assert(condition: unknown, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

const config = getDefaultConfig('enterprise_wechat_aibot') as any;

assert('enterprise_wechat_aibot' in nodeConfig, 'nodeConfig must register enterprise_wechat_aibot');
assert(
  (TRIGGER_NODE_TYPES as readonly string[]).includes('enterprise_wechat_aibot'),
  'enterprise_wechat_aibot must be a trigger node',
);

const applicationCategory = nodeCategories.find((category) => category.key === 'applications');
assert(applicationCategory, 'nodeCategories must include applications category');
assert(
  applicationCategory.items.some((item) => item.type === 'enterprise_wechat_aibot'),
  'applications category must show enterprise_wechat_aibot in the node library',
);

assert(config.connectionMode === 'webhook', 'connectionMode must default to webhook');
assert(config.webhook?.token === '', 'webhook.token must default to empty string');
assert(config.webhook?.encodingAESKey === '', 'webhook.encodingAESKey must default to empty string');
assert(config.webhook?.aibotid === '', 'webhook.aibotid must default to empty string');
assert(config.websocket?.botId === '', 'websocket.botId must be reserved');
assert(config.websocket?.secret === '', 'websocket.secret must be reserved');
assert(config.inputParams === 'last_message', 'inputParams must remain last_message');
assert(config.outputParams === 'last_message', 'outputParams must remain last_message');

const configuredSummary = formatConfigInfo({
  label: '企微机器人',
  type: 'enterprise_wechat_aibot',
  config: {
    ...config,
    webhook: {
      token: 'token',
      encodingAESKey: 'encoding-aes-key',
      aibotid: 'bot-id',
    },
  },
}, (key: string) => key);

assert(configuredSummary !== 'chatflow.notConfigured', 'configured enterprise_wechat_aibot must not render as not configured');
assert(configuredSummary.includes('Token'), 'configured enterprise_wechat_aibot summary must mention Token');
assert(configuredSummary.includes('EncodingAESKey'), 'configured enterprise_wechat_aibot summary must mention EncodingAESKey');
