import { ReactNode } from 'react';
import { ButtonProps } from 'antd';
import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';

export interface CustomChatSSEProps {
  handleSendMessage?: (message: string, currentMessages?: any[]) => Promise<{ url: string; payload: any } | null>;
  showMarkOnly?: boolean;
  initialMessages?: CustomChatMessage[];
  mode?: 'chat' | 'display';
  guide?: string;
  useAGUIProtocol?: boolean;
  showHeader?: boolean;
  requirePermission?: boolean;
}

export type ActionRender = (
  _: any, 
  info: { 
    components: { 
      SendButton: React.ComponentType<ButtonProps>; 
      LoadingButton: React.ComponentType<ButtonProps>; 
    }; 
  }
) => ReactNode;

export interface SSEChunk {
  choices: Array<{
    delta: {
      content?: string;
    };
    index: number;
    finish_reason: string | null;
  }>;
  id: string;
  object: string;
  created: number;
}

// AG-UI Protocol Message Types
export interface AGUIMessage {
  type: 'RUN_STARTED' | 'TEXT_MESSAGE_START' | 'TEXT_MESSAGE_CONTENT' | 'TEXT_MESSAGE_END' | 'RUN_FINISHED' | 'TOOL_CALL_START' | 'TOOL_CALL_ARGS' | 'TOOL_CALL_END' | 'TOOL_CALL_RESULT' | 'ERROR' | 'RUN_ERROR';
  timestamp: number;
  threadId?: string;
  runId?: string;
  messageId?: string;
  role?: string;
  delta?: string;
  toolCallId?: string;
  toolCallName?: string;
  parentMessageId?: string;
  content?: string;
  error?: string;
  message?: string;
  code?: string;
}

export interface ReferenceModalState {
  visible: boolean;
  loading: boolean;
  title: string;
  content: string;
}

export interface DrawerContentState {
  visible: boolean;
  title: string;
  content: string;
  chunkType?: "Document" | "QA" | "Graph";
  graphData?: { nodes: any[], edges: any[] };
}

export interface GuideParseResult {
  text: string;
  items: string[];
  renderedHtml: string;
}

export interface ReferenceParams {
  refNumber: string;
  chunkId: string | null;
  knowledgeId: string | null;
}

export interface MessageActionsProps {
  message: CustomChatMessage;
  onCopy: (content: string) => void;
  onRegenerate: (id: string) => void;
  onDelete: (id: string) => void;
  onMark: (message: CustomChatMessage) => void;
  showMarkOnly?: boolean;
}

export interface AnnotationModalProps {
  visible: boolean;
  showMarkOnly?: boolean;
  annotation: Annotation | null;
  onSave: (annotation?: Annotation) => void;
  onRemove: (id: string | undefined) => void;
  onCancel: () => void;
}