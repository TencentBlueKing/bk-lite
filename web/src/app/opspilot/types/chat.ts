import { ReactNode } from 'react';
import { ButtonProps } from 'antd';
import { CustomChatMessage, Annotation } from '@/app/opspilot/types/global';

export interface CustomChatSSEProps {
  handleSendMessage?: (message: string, currentMessages?: any[]) => Promise<{ url: string; payload: any } | null>;
  showMarkOnly?: boolean;
  initialMessages?: CustomChatMessage[];
  mode?: 'chat' | 'display';
  guide?: string;
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