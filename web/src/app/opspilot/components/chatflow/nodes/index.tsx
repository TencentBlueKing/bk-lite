import React from 'react';
import { BaseNode } from './BaseNode';
import { nodeConfig } from '@/app/opspilot/constants/chatflow';

export const TimeTriggerNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.celery.icon} color={nodeConfig.celery.color} hasOutput={true} />
);

export const RestfulApiNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.restful.icon} color={nodeConfig.restful.color} hasOutput={true} />
);

export const OpenAIApiNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.openai.icon} color={nodeConfig.openai.color} hasOutput={true} />
);

export const AgentsNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.agents.icon} color={nodeConfig.agents.color} hasInput={true} hasOutput={true} />
);

export const HttpRequestNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.http.icon} color={nodeConfig.http.color} hasInput={true} hasOutput={true} />
);

export const IfConditionNode = (props: any) => (
  <BaseNode
    {...props}
    icon={nodeConfig.condition.icon}
    color={nodeConfig.condition.color}
    hasInput={true}
    hasOutput={false}
    hasMultipleOutputs={true}
  />
);

export const NotificationNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.notification.icon} color={nodeConfig.notification.color} hasInput={true} hasOutput={true} />
);

export const EnterpriseWechatNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.enterprise_wechat.icon} color={nodeConfig.enterprise_wechat.color} hasOutput={true} />
);

export const DingtalkNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.dingtalk.icon} color={nodeConfig.dingtalk.color} hasOutput={true} />
);

export const WechatOfficialNode = (props: any) => (
  <BaseNode {...props} icon={nodeConfig.wechat_official.icon} color={nodeConfig.wechat_official.color} hasOutput={true} />
);
