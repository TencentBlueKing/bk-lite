import { CustomChatMessage } from '@/app/opspilot/types/global';

export interface Studio {
  id: number;
  name: string;
  introduction: string;
  created_by: string;
  team: string[];
  team_name: string[];
  online: boolean;
  [key: string]: any;
}

export interface ModifyStudioModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: Studio) => void;
  initialValues?: Studio | null;
}

interface ChannelConfig {
  [key: string]: any;
}

export interface ChannelProps {
  id: string;
  name: string;
  enabled: boolean;
  icon: string;
  channel_config: ChannelConfig;
}

export interface LogRecord {
  key: string;
  title: string;
  createdTime: string;
  updatedTime: string;
  user: string;
  channel: string;
  count: number;
  ids?: number[];
  conversation?: CustomChatMessage[];
}

export interface Channel {
  id: string;
  name: string;
}
