import type { FormInstance, UploadFile, UploadProps } from 'antd';

export interface TranslationFunction {
  (key: string): string;
}

export interface KeyValueRow {
  key: string;
  value: string;
}

export interface KeyValueEditorProps {
  rows: KeyValueRow[];
  addRow: () => void;
  removeRow: (index: number) => void;
  updateRow: (index: number, field: 'key' | 'value', value: string) => void;
}

export interface BaseNodeConfigProps {
  t: TranslationFunction;
}

export interface CeleryNodeConfigProps extends BaseNodeConfigProps {
  frequency: string;
  onFrequencyChange: (value: string) => void;
}

export interface HttpNodeConfigProps extends BaseNodeConfigProps {
  paramRows: KeyValueEditorProps;
  headerRows: KeyValueEditorProps;
}

export interface AgentsNodeConfigProps extends BaseNodeConfigProps {
  skills: Array<{ id: string; name: string }>;
  loadingSkills: boolean;
  uploadedFiles: UploadFile[];
  setUploadedFiles: (files: UploadFile[]) => void;
  uploadProps: UploadProps;
  form: FormInstance;
}

export interface ApiInfoNodeConfigProps extends BaseNodeConfigProps {
  nodeType: string;
  botId: string;
  nodeId: string;
  copyApiUrl: () => void;
}

export interface WebChatNodeConfigProps extends BaseNodeConfigProps {
  form: FormInstance;
}

export type MobileNodeConfigProps = BaseNodeConfigProps;

export interface ConditionNodeConfigProps extends BaseNodeConfigProps {
  nodes: Array<{ id: string; data: { type?: string; label?: string } }>;
}

export interface IntentClassificationNodeConfigProps extends BaseNodeConfigProps {
  skills: Array<{ id: string; name: string }>;
  loadingSkills: boolean;
}

export interface NotificationNodeConfigProps extends BaseNodeConfigProps {
  notificationType: string;
  setNotificationType: (type: string) => void;
  notificationChannels: Array<{ id: string; name: string }>;
  loadingChannels: boolean;
  loadChannels: (type: string) => void;
  allUsers: Array<{ id: string; username: string; name?: string; display_name?: string }>;
  loadingUsers: boolean;
  form: FormInstance;
}

export type EnterpriseWechatNodeConfigProps = BaseNodeConfigProps;

export type DingtalkNodeConfigProps = BaseNodeConfigProps;

export type WechatOfficialNodeConfigProps = BaseNodeConfigProps;
