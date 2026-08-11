/**
 * AG-UI Integration Layer
 * Bridges @ag-ui/core with the existing SSE-based chat system
 */

import { Observable, Subject } from 'rxjs';
import { parseLegacyMessage, type LegacyMessage } from './legacyMessage';
import {
  Message,
  ActivityMessage,
  EventSchemas,
  EventType,
  TextMessageStartEvent,
  TextMessageContentEvent,
  TextMessageChunkEvent,
  TextMessageEndEvent,
  ThinkingStartEvent,
  ThinkingEndEvent,
  RunStartedEvent,
  RunFinishedEvent,
  RunErrorEvent,
  ToolCallStartEvent,
  ToolCallArgsEvent,
  ToolCallEndEvent,
  ToolCallResultEvent,
} from '@ag-ui/core';

export interface AGUIConfig {
  enabled?: boolean;
  debug?: boolean;
}

export type AGUIEvent =
  | TextMessageStartEvent
  | TextMessageContentEvent
  | TextMessageChunkEvent
  | TextMessageEndEvent
  | ThinkingStartEvent
  | ThinkingEndEvent
  | RunStartedEvent
  | RunFinishedEvent
  | RunErrorEvent
  | ToolCallStartEvent
  | ToolCallArgsEvent
  | ToolCallEndEvent
  | ToolCallResultEvent;

export interface AGUIEventResult {
  type: 'agui-event';
  event: AGUIEvent;
}

export interface LegacyMessageResult {
  type: 'legacy-message';
  message: LegacyMessage;
}

export interface IgnoredEventResult {
  type: 'ignored';
}

export type AGUIProcessResult = AGUIEventResult | LegacyMessageResult | IgnoredEventResult;

const SUPPORTED_EVENT_TYPES: ReadonlySet<EventType> = new Set([
  EventType.TEXT_MESSAGE_START,
  EventType.TEXT_MESSAGE_CONTENT,
  EventType.TEXT_MESSAGE_CHUNK,
  EventType.TEXT_MESSAGE_END,
  EventType.THINKING_START,
  EventType.THINKING_END,
  EventType.RUN_STARTED,
  EventType.RUN_FINISHED,
  EventType.RUN_ERROR,
  EventType.TOOL_CALL_START,
  EventType.TOOL_CALL_ARGS,
  EventType.TOOL_CALL_END,
  EventType.TOOL_CALL_RESULT,
]);
const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set(Object.values(EventType));
const LEGACY_RUN_CONTEXT_ID = 'legacy';

function isSupportedAGUIEvent(event: unknown): event is AGUIEvent {
  return (
    event !== null &&
    typeof event === 'object' &&
    'type' in event &&
    SUPPORTED_EVENT_TYPES.has((event as { type: EventType }).type)
  );
}

function normalizeLegacyEvent(data: Record<string, unknown>): Record<string, unknown> {
  if (data.type === 'ERROR') {
    return {
      type: EventType.RUN_ERROR,
      message:
        typeof data.error === 'string'
          ? data.error
          : typeof data.message === 'string'
            ? data.message
            : 'An error occurred',
      ...(typeof data.timestamp === 'number' ? { timestamp: data.timestamp } : {}),
    };
  }

  if (data.type === EventType.RUN_STARTED || data.type === EventType.RUN_FINISHED) {
    return {
      ...data,
      threadId: data.threadId ?? LEGACY_RUN_CONTEXT_ID,
      runId: data.runId ?? LEGACY_RUN_CONTEXT_ID,
    };
  }

  return data;
}

/**
 * AG-UI Event Handler
 * Processes AG-UI protocol events and converts them to our message format
 */
export class AGUIHandler {
  private events$ = new Subject<AGUIEvent>();
  private config: AGUIConfig;
  private debug: boolean;

  constructor(config: AGUIConfig = {}) {
    this.config = {
      enabled: true,
      debug: false,
      ...config,
    };
    this.debug = this.config.debug || false;
  }

  /**
   * Get observable stream of AG-UI events
   */
  getEventStream(): Observable<AGUIEvent> {
    return this.events$.asObservable();
  }

  /**
   * Process SSE data and convert to AG-UI events
   */
  processSSEData(data: unknown): AGUIProcessResult {
    if (!this.config.enabled) {
      return this.processLegacyMessage(data);
    }

    if (this.isEventRecord(data)) {
      const eventType = data.type;
      const event = this.parseAGUIEvent(data);
      if (event) {
        this.events$.next(event);
        return { type: 'agui-event', event };
      }
      if (
        typeof eventType === 'string' &&
        (eventType === 'ERROR' || KNOWN_EVENT_TYPES.has(eventType))
      ) {
        return { type: 'ignored' };
      }
    }

    return this.processLegacyMessage(data);
  }

  private processLegacyMessage(data: unknown): LegacyMessageResult | IgnoredEventResult {
    const message = parseLegacyMessage(data);
    return message ? { type: 'legacy-message', message } : { type: 'ignored' };
  }

  /**
   * Check if data follows AG-UI protocol
   */
  private isEventRecord(data: unknown): data is Record<string, unknown> {
    return (
      data !== null &&
      typeof data === 'object' &&
      !Array.isArray(data) &&
      'type' in data &&
      typeof (data as { type: unknown }).type === 'string'
    );
  }

  /**
   * Parse AG-UI event from SSE data
   */
  private parseAGUIEvent(data: Record<string, unknown>): AGUIEvent | null {
    const candidate = normalizeLegacyEvent(data);
    const parsed = EventSchemas.safeParse(candidate);

    if (!parsed.success || !isSupportedAGUIEvent(parsed.data)) {
      if (this.debug) {
        console.warn('[AG-UI] Invalid or unsupported event:', data.type);
      }
      return null;
    }

    return parsed.data;
  }

  /**
   * Convert AG-UI message to our internal format
   */
  convertAGUIMessage(aguiMessage: Message | ActivityMessage): {
    id: string;
    type: string;
    content: string;
    sender: 'user' | 'bot';
    timestamp: number;
  } {
    const content = this.extractMessageContent(aguiMessage);
    const sender = aguiMessage.role === 'user' ? 'user' : 'bot';

    return {
      id: aguiMessage.id,
      type: 'text',
      content,
      sender,
      timestamp: Date.now(),
    };
  }

  /**
   * Extract text content from AG-UI message
   */
  private extractMessageContent(message: Message | ActivityMessage): string {
    if (!message.content) {
      return '';
    }

    if (typeof message.content === 'string') {
      return message.content;
    }

    // Handle array of content parts
    if (Array.isArray(message.content)) {
      return message.content
        .map((part) => {
          if (typeof part === 'string') return part;
          if (part.type === 'text') return part.text;
          return '';
        })
        .join('');
    }

    return '';
  }

  /**
   * Destroy handler
   */
  destroy(): void {
    this.events$.complete();
  }
}
