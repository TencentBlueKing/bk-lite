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
import {
  createStreamingFrameBatcher,
  type FrameScheduler,
} from './streamingFrameBatcher';

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
  frameScheduler?: FrameScheduler;
  streamingTextBatchingRef?: MutableRefObject<boolean>;
}

export interface AGUIEventDispatcher {
  (event: AGUIEvent): void;
  flushPendingText(): void;
  cancelPendingText(): void;
}

/** Show the extra typing bubble only while waiting for the first bot message. */
export function shouldShowTypingPlaceholder(
  isLoading: boolean,
  isThinking: boolean,
  messages: Array<{ sender: string }>
): boolean {
  if (!isLoading && !isThinking) {
    return false;
  }
  const last = messages[messages.length - 1];
  return last?.sender !== 'bot';
}

/** Create the AG-UI protocol event dispatcher used by Chat. */
export function createAGUIEventHandler(deps: AGUIEventHandlerDeps): AGUIEventDispatcher {
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
    frameScheduler,
    streamingTextBatchingRef,
  } = deps;
  let streamingSegmentContent = '';

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

  const applyStreamingText = (segmentText: string) => {
    const messageId = currentMessageIdRef.current;
    setMessages((prev) =>
      mapMessageChunks(
        prev,
        messageId,
        (chunks) => upsertTextChunk(chunks, segmentText),
        streamingContentRef.current
      )
    );
    syncSessionChunks(
      sessionManagerRef.current?.getSession(),
      messageId,
      (chunks) => upsertTextChunk(chunks, segmentText),
      streamingContentRef.current
    );
  };

  const textBatcher = createStreamingFrameBatcher(
    applyStreamingText,
    frameScheduler,
    () => streamingTextBatchingRef?.current !== false
  );

  const flushAndPersistPendingText = () => {
    textBatcher.flush();
    if (currentMessageIdRef.current) {
      sessionManagerRef.current?.saveSession();
    }
  };

  const applyThinkingDelta = (delta: string) => {
    ensureCurrentMessage();
    const messageId = currentMessageIdRef.current;
    if (!messageId) return;
    const patch = (message: Message): Message => {
      if (message.id !== messageId) return message;
      const previous = typeof message.metadata?.thinking === 'string' ? message.metadata.thinking : '';
      return {
        ...message,
        metadata: {
          ...message.metadata,
          thinking: previous + delta,
          isThinking: true,
        },
      };
    };
    setMessages((prev) => prev.map(patch));
    const session = sessionManagerRef.current?.getSession();
    if (session) {
      session.messages = session.messages.map(patch);
    }
  };

  const setMessageThinking = (thinking: boolean) => {
    const messageId = currentMessageIdRef.current;
    if (!messageId) return;
    const patch = (message: Message): Message => {
      if (message.id !== messageId) return message;
      return {
        ...message,
        metadata: {
          ...message.metadata,
          isThinking: thinking,
        },
      };
    };
    setMessages((prev) => prev.map(patch));
    const session = sessionManagerRef.current?.getSession();
    if (session) {
      session.messages = session.messages.map(patch);
    }
  };

  const applyToolPatch = (toolCallId: string, patch: Partial<ToolCall>) => {
    textBatcher.flush();
    const messageId = currentMessageIdRef.current;
    setMessages((prev) =>
      mapMessageChunks(prev, messageId, (chunks) => patchToolCall(chunks, toolCallId, patch))
    );
    syncSessionChunks(sessionManagerRef.current?.getSession(), messageId, (chunks) =>
      patchToolCall(chunks, toolCallId, patch)
    );
  };

  const dispatch = (event: AGUIEvent) => {
    switch (event.type) {
      case 'RUN_STARTED':
        // Preserve the partial response just like immediate mode, while also
        // cancelling the queued frame before the new run takes ownership.
        textBatcher.flush();
        setIsThinking(true);
        stateMachineRef.current?.transitionToChatting();
        streamingContentRef.current = '';
        streamingSegmentContent = '';
        currentMessageIdRef.current = null;
        setIsLoading(true);
        break;

      case 'THINKING_START':
        ensureCurrentMessage();
        setIsThinking(true);
        setMessageThinking(true);
        break;

      case 'THINKING':
        setIsThinking(true);
        applyThinkingDelta(event.delta || '');
        break;

      case 'THINKING_END':
        setIsThinking(false);
        setMessageThinking(false);
        break;

      case 'RUN_ERROR': {
        textBatcher.flush();
        setIsThinking(false);
        const error = event.message || 'Unknown error';
        const errorContent = `\n\n❌ **错误**: ${error}`;

        if (currentMessageIdRef.current) {
          streamingContentRef.current += errorContent;
          streamingSegmentContent += errorContent;
          textBatcher.schedule(streamingSegmentContent);
          textBatcher.flush();
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
        streamingSegmentContent = '';
        setIsThinking(false);
        setMessageThinking(false);
        setIsLoading(true);
        break;
      }

      case 'TEXT_MESSAGE_CONTENT': {
        ensureCurrentMessage();
        streamingContentRef.current += event.delta;
        streamingSegmentContent += event.delta;
        textBatcher.schedule(streamingSegmentContent);
        setIsThinking(false);
        break;
      }

      case 'TEXT_MESSAGE_CHUNK': {
        if (event.role === 'user') {
          break;
        }
        ensureCurrentMessage();
        streamingContentRef.current += event.delta || '';
        streamingSegmentContent += event.delta || '';
        textBatcher.schedule(streamingSegmentContent);
        setIsThinking(false);
        setIsLoading(true);
        break;
      }

      case 'TEXT_MESSAGE_END':
        flushAndPersistPendingText();
        break;

      case 'TOOL_CALL_START': {
        textBatcher.flush();
        streamingSegmentContent = '';
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
        flushAndPersistPendingText();
        setIsThinking(false);
        setMessageThinking(false);
        setIsLoading(false);
        stateMachineRef.current?.transition('connected');
        break;

      default:
        break;
    }
  };

  dispatch.flushPendingText = flushAndPersistPendingText;
  dispatch.cancelPendingText = () => textBatcher.cancel();
  return dispatch;
}
