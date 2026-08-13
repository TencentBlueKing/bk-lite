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
    switch (event.type) {
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
        const error = event.message || 'Unknown error';
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
        if (event.role === 'user') {
          break;
        }
        ensureCurrentMessage();
        streamingContentRef.current = '';
        setIsThinking(false);
        setIsLoading(true);
        break;
      }

      case 'TEXT_MESSAGE_CONTENT': {
        if (!currentMessageIdRef.current) {
          console.warn('Received CONTENT without START, ignoring');
          break;
        }
        streamingContentRef.current += event.delta;
        applyStreamingText(streamingContentRef.current);
        break;
      }

      case 'TEXT_MESSAGE_CHUNK': {
        if (event.role === 'user') {
          break;
        }
        ensureCurrentMessage();
        streamingContentRef.current += event.delta || '';
        applyStreamingText(streamingContentRef.current);
        setIsThinking(false);
        setIsLoading(true);
        break;
      }

      case 'TEXT_MESSAGE_END':
        if (currentMessageIdRef.current && sessionManagerRef.current) {
          sessionManagerRef.current.saveSession();
        }
        break;

      case 'TOOL_CALL_START': {
        const newToolCall: ToolCall = {
          id: event.toolCallId || generateId(),
          name: event.toolCallName || 'Unknown Tool',
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
        applyToolPatch(event.toolCallId || '', {
          args: event.delta,
        });
        break;
      }

      case 'TOOL_CALL_END':
        applyToolPatch(event.toolCallId || '', { status: 'completed' });
        break;

      case 'TOOL_CALL_RESULT':
        applyToolPatch(event.toolCallId || '', {
          result: event.content,
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
