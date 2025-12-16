/**
 * AG-UI Integration Layer
 * Bridges @ag-ui/core with the existing SSE-based chat system
 */

import { Observable, Subject } from 'rxjs';
import {
  Message,
  ActivityMessage,
  TextMessageStartEvent,
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
  processSSEData(data: any): {
    type: 'agui-event' | 'legacy-message';
    event?: AGUIEvent;
    message?: any;
  } {
    if (!this.config.enabled) {
      return { type: 'legacy-message', message: data };
    }

    // Check if data follows AG-UI protocol
    if (this.isAGUIEvent(data)) {
      const event = this.parseAGUIEvent(data);
      if (event) {
        this.events$.next(event);
        return { type: 'agui-event', event };
      }
    }

    // Fallback to legacy message format
    return { type: 'legacy-message', message: data };
  }

  /**
   * Check if data follows AG-UI protocol
   */
  private isAGUIEvent(data: any): boolean {
    return (
      data &&
      typeof data === 'object' &&
      'type' in data &&
      typeof data.type === 'string' &&
      (
        data.type.startsWith('TEXT_MESSAGE_') ||
        data.type.startsWith('THINKING_') ||
        data.type.startsWith('RUN_') ||
        data.type.startsWith('TOOL_CALL_') ||
        data.type === 'ERROR' ||
        data.type.includes('.')
      )
    );
  }

  /**
   * Parse AG-UI event from SSE data
   */
  private parseAGUIEvent(data: any): AGUIEvent | null {
    try {
      const eventType = data.type as string;

      // Map AG-UI events to our types
      switch (eventType) {
        case 'TEXT_MESSAGE_START':
          return data as TextMessageStartEvent;
          
        case 'TEXT_MESSAGE_CONTENT':
          return data as any;
          
        case 'TEXT_MESSAGE_END':
          return data as TextMessageEndEvent;
          
        case 'THINKING_START':
          return data as ThinkingStartEvent;
          
        case 'THINKING_END':
          return data as ThinkingEndEvent;
          
        case 'RUN_STARTED':
          return data as RunStartedEvent;
          
        case 'RUN_FINISHED':
          return data as RunFinishedEvent;
          
        case 'RUN_ERROR':
        case 'ERROR':
          return { type: 'RUN_ERROR', message: data.error || data.message || 'An error occurred', timestamp: data.timestamp } as RunErrorEvent;
          
        case 'TOOL_CALL_START':
          return data as ToolCallStartEvent;
          
        case 'TOOL_CALL_ARGS':
          return data as ToolCallArgsEvent;
          
        case 'TOOL_CALL_END':
          return data as ToolCallEndEvent;
          
        case 'TOOL_CALL_RESULT':
          return data as ToolCallResultEvent;
          
        default:
          if (this.debug) {
            console.warn('[AG-UI] Unknown event type:', eventType);
          }
          return null;
      }
    } catch (error) {
      console.error('[AG-UI] Failed to parse event:', error);
      return null;
    }
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
