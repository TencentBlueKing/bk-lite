import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import {
  generateId,
  type Message,
  type SessionManager,
  type StateMachine,
} from '@webchat/core';
import type { AGUIEvent } from './agui';
import type { ToolCall } from './contentChunks';
import {
  appendToolCallChunk,
  mapMessageChunks,
  patchToolCall,
  syncSessionChunks,
  upsertTextChunk,
} from './contentChunks';

export interface AGUIEventHandlerDeps {
  currentMessageIdRef: MutableRefObject<string | null>;
  streamingContentRef: MutableRefObject<string>;
  sessionManagerRef: MutableRefObject<SessionManager | null>;
  stateMachineRef: MutableRefObject<StateMachine | null>;
  onMessageReceivedRef: MutableRefObject<((message: Message) => void) | undefined>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setIsLoading: Dispatch<SetStateAction<boolean>>;
  setIsThinking: Dispatch<SetStateAction<boolean>>;
  addMessage: (message: Message) => void;
}

type AGUIEventWithExtras = AGUIEvent & {
  role?: string;
  sender?: string;
  delta?: string;
  content?: string;
  message?: string;
  toolCallId?: string;
  toolCallName?: string;
  name?: string;
  arguments?: unknown;
};

/** Create the AG-UI protocol event dispatcher used by Chat. */
export function createAGUIEventHandler(deps: AGUIEventHandlerDeps) {
  const {
    currentMessageIdRef,
    streamingContentRef,
    sessionManagerRef,
    stateMachineRef,
    onMessageReceivedRef,
    setMessages,
    setIsLoading,
    setIsThinking,
    addMessage,
  } = deps;

  const ensureCurrentMessage = () => {
    if (currentMessageIdRef.current) return;
    const newAssistantMsg: Message = {
      id: generateId(),
      type: 'text',
      content: '',
      sender: 'bot',
      timestamp: Date.now(),
      metadata: { contentChunks: [] },
    };
    currentMessageIdRef.current = newAssistantMsg.id;
    setMessages((prev) => [...prev, newAssistantMsg]);
    sessionManagerRef.current?.addMessage(newAssistantMsg);
    onMessageReceivedRef.current?.(newAssistantMsg);
  };

  const applyStreamingText = (text: string) => {
    const messageId = currentMessageIdRef.current;
    setMessages((prev) =>
      mapMessageChunks(prev, messageId, (chunks) => upsertTextChunk(chunks, text), text)
    );
    syncSessionChunks(
      sessionManagerRef.current?.getSession(),
      messageId,
      (chunks) => upsertTextChunk(chunks, text),
      text
    );
  };

  const applyToolPatch = (toolCallId: string, patch: Partial<ToolCall>) => {
    const messageId = currentMessageIdRef.current;
    setMessages((prev) =>
      mapMessageChunks(prev, messageId, (chunks) => patchToolCall(chunks, toolCallId, patch))
    );
    syncSessionChunks(sessionManagerRef.current?.getSession(), messageId, (chunks) =>
      patchToolCall(chunks, toolCallId, patch)
    );
  };

  return (event: AGUIEvent) => {
    const typedEvent = event as AGUIEventWithExtras;
    const eventType = typedEvent.type;

    switch (eventType) {
      case 'RUN_STARTED':
        setIsThinking(true);
        stateMachineRef.current?.transitionToChatting();
        streamingContentRef.current = '';
        currentMessageIdRef.current = null;
        setIsLoading(true);
        break;

      case 'THINKING_START':
        setIsThinking(true);
        break;

      case 'THINKING_END':
        setIsThinking(false);
        break;

      case 'RUN_ERROR': {
        setIsThinking(false);
        const error = typedEvent.message || 'Unknown error';
        const errorContent = `\n\n❌ **错误**: ${error}`;

        if (currentMessageIdRef.current) {
          streamingContentRef.current += errorContent;
          applyStreamingText(streamingContentRef.current);
          sessionManagerRef.current?.saveSession();
        } else {
          addMessage({
            id: generateId(),
            type: 'text',
            content: `❌ **错误**\n\n${error}`,
            sender: 'bot',
            timestamp: Date.now(),
          });
        }
        break;
      }

      case 'TEXT_MESSAGE_START': {
        const startRole = typedEvent.role || typedEvent.sender;
        if (startRole === 'user') {
          break;
        }
        ensureCurrentMessage();
        streamingContentRef.current = '';
        setIsThinking(false);
        setIsLoading(true);
        break;
      }

      case 'TEXT_MESSAGE_CONTENT': {
        const delta = typedEvent.delta || typedEvent.content || '';
        const contentRole = typedEvent.role || typedEvent.sender;
        if (contentRole === 'user') {
          break;
        }
        if (!currentMessageIdRef.current) {
          console.warn('Received CONTENT without START, ignoring');
          break;
        }
        streamingContentRef.current += delta;
        applyStreamingText(streamingContentRef.current);
        break;
      }

      case 'TEXT_MESSAGE_END':
        if (currentMessageIdRef.current && sessionManagerRef.current) {
          sessionManagerRef.current.saveSession();
        }
        break;

      case 'TOOL_CALL_START': {
        const newToolCall: ToolCall = {
          id: typedEvent.toolCallId || generateId(),
          name: typedEvent.toolCallName || typedEvent.name || 'Unknown Tool',
          status: 'running',
        };
        ensureCurrentMessage();
        const messageId = currentMessageIdRef.current;
        setMessages((prev) =>
          mapMessageChunks(prev, messageId, (chunks) => {
            const next = appendToolCallChunk(chunks, newToolCall);
            if (next === null) {
              console.warn('Tool call already exists:', newToolCall.id);
            }
            return next;
          })
        );
        syncSessionChunks(sessionManagerRef.current?.getSession(), messageId, (chunks) =>
          appendToolCallChunk(chunks, newToolCall)
        );
        break;
      }

      case 'TOOL_CALL_ARGS': {
        const rawArgs = typedEvent.delta ?? typedEvent.arguments;
        applyToolPatch(typedEvent.toolCallId || '', {
          args:
            typeof rawArgs === 'string'
              ? rawArgs
              : rawArgs === undefined
                ? undefined
                : JSON.stringify(rawArgs),
        });
        break;
      }

      case 'TOOL_CALL_END':
        applyToolPatch(typedEvent.toolCallId || '', { status: 'completed' });
        break;

      case 'TOOL_CALL_RESULT':
        applyToolPatch(typedEvent.toolCallId || '', {
          result:
            typeof typedEvent.content === 'string'
              ? typedEvent.content
              : typedEvent.content === undefined
                ? undefined
                : JSON.stringify(typedEvent.content),
        });
        break;

      case 'RUN_FINISHED':
        if (currentMessageIdRef.current && sessionManagerRef.current) {
          sessionManagerRef.current.saveSession();
        }
        setIsThinking(false);
        stateMachineRef.current?.transition('connected');
        break;

      default:
        break;
    }
  };
}
