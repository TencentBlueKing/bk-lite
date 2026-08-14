import { Message, EventListener, MessageEvent } from './types';
import { SSEStreamParser } from './sseParser';

/**
 * SSEHandler: Handles Server-Sent Events for streaming chat responses
 */
export class SSEHandler {
  private eventSource: EventSource | null = null;
  private abortController: AbortController | null = null;
  private listeners: Map<string, Set<EventListener<unknown>>> = new Map();
  private parser = new SSEStreamParser();
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number;
  private reconnectDelay: number;
  private url: string = '';
  private connectionGeneration: number = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectWaitResolve: (() => void) | null = null;

  constructor(maxReconnectAttempts: number = 5, reconnectDelay: number = 1000) {
    this.maxReconnectAttempts = maxReconnectAttempts;
    this.reconnectDelay = reconnectDelay;
  }

  /**
   * Connect to SSE endpoint
   */
  public connect(url: string, headers?: Record<string, string>): Promise<void> {
    this.url = url;
    this.clearReconnectTimer();
    this.closeActiveConnection();
    this.reconnectAttempts = 0;
    const generation = ++this.connectionGeneration;
    return this.connectForGeneration(url, headers, generation);
  }

  private connectForGeneration(
    url: string,
    headers: Record<string, string> | undefined,
    generation: number
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        // Note: EventSource doesn't support custom headers directly
        // For custom headers, use fetch with ReadableStream
        if (headers) {
          this.connectWithFetch(url, headers, generation).then(resolve).catch(reject);
          return;
        }

        const eventSource = new EventSource(url);
        this.eventSource = eventSource;

        eventSource.onopen = () => {
          if (!this.isCurrentEventSource(eventSource, generation)) return;
          console.log('SSE connection opened');
          this.reconnectAttempts = 0;
          this.emit('open', { timestamp: Date.now() });
          resolve();
        };

        eventSource.onmessage = (event) => {
          if (!this.isCurrentEventSource(eventSource, generation)) return;
          this.emitParsedPayload(event.data);
        };

        eventSource.onerror = (error) => {
          if (!this.isCurrentEventSource(eventSource, generation)) return;
          console.error('SSE error:', error);
          this.handleError(error);
          if (!this.isCurrentEventSource(eventSource, generation)) return;
          this.closeEventSource(eventSource);
          if (this.eventSource === eventSource) {
            this.eventSource = null;
          }
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnect(url, headers, generation);
          } else {
            reject(new Error('Max reconnection attempts reached'));
          }
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Connect using fetch + ReadableStream (supports custom headers)
   */
  private async connectWithFetch(
    url: string,
    headers: Record<string, string>,
    generation: number
  ): Promise<void> {
    const abortController = new AbortController();
    this.abortController = abortController;
    this.parser.reset();
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'text/event-stream',
          ...headers,
        },
        signal: abortController.signal,
      });

      if (!this.isCurrentFetch(abortController, generation)) return;
      if (!response.ok || !response.body) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      this.reconnectAttempts = 0;
      this.emit('open', { timestamp: Date.now() });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      for (;;) {
        const { done, value } = await reader.read();
        if (done || !this.isCurrentFetch(abortController, generation)) break;

        const chunk = decoder.decode(value, { stream: true });
        this.processChunk(chunk, abortController, generation);
      }
    } catch (error) {
      if (
        (error as Error).name !== 'AbortError' &&
        this.isCurrentFetch(abortController, generation)
      ) {
        console.error('Fetch SSE error:', error);
        this.handleError(error);
        if (!this.isCurrentFetch(abortController, generation)) return;
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          await this.waitForReconnect(this.reconnectDelay);
          if (generation === this.connectionGeneration) {
            await this.connectWithFetch(url, headers, generation);
          }
        }
      }
    }
  }

  /**
   * Process incoming chunk through the shared SSE parser
   */
  private processChunk(
    chunk: string,
    abortController: AbortController,
    generation: number
  ): void {
    for (const payload of this.parser.push(chunk)) {
      if (!this.isCurrentFetch(abortController, generation)) break;
      this.emitMessage(this.payloadToMessage(payload));
    }
  }

  /**
   * Emit a MessageEvent for EventSource data (already stripped of `data:` prefix)
   */
  private emitParsedPayload(data: string): void {
    if (!data.trim()) {
      return;
    }
    try {
      this.emitMessage(this.payloadToMessage(JSON.parse(data)));
    } catch {
      this.emitMessage(this.payloadToMessage(data));
    }
  }

  private payloadToMessage(payload: unknown): Message {
    if (typeof payload === 'object' && payload !== null) {
      const json = payload as Record<string, unknown>;
      const content: Message['content'] =
        typeof json.content === 'string' || Array.isArray(json.content)
          ? (json.content as Message['content'])
          : JSON.stringify(json);
      const sender = json.sender === 'user' ? 'user' : 'bot';
      return {
        id: (typeof json.id === 'string' ? json.id : undefined) || `msg_${Date.now()}`,
        type: 'text',
        content,
        sender,
        timestamp: typeof json.timestamp === 'number' ? json.timestamp : Date.now(),
        metadata:
          typeof json.metadata === 'object' && json.metadata !== null
            ? (json.metadata as Message['metadata'])
            : undefined,
      };
    }

    return {
      id: `msg_${Date.now()}`,
      type: 'text',
      content: String(payload),
      sender: 'bot',
      timestamp: Date.now(),
    };
  }

  private emitMessage(message: Message): void {
    this.emit('message', { message, timestamp: Date.now() } as MessageEvent);
  }

  /**
   * Handle connection error
   */
  private handleError(error: unknown): void {
    this.emit('error', { error, timestamp: Date.now() });
  }

  /**
   * Reconnect to SSE
   */
  private reconnect(
    url: string,
    headers: Record<string, string> | undefined,
    generation: number
  ): void {
    this.reconnectAttempts++;
    console.log(
      `Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`
    );

    this.clearReconnectTimer();
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (generation !== this.connectionGeneration) return;
      this.connectForGeneration(url, headers, generation).catch((error) => {
        console.error('Reconnection failed:', error);
      });
    }, this.reconnectDelay * this.reconnectAttempts);
  }

  private isCurrentEventSource(eventSource: EventSource, generation: number): boolean {
    return generation === this.connectionGeneration && this.eventSource === eventSource;
  }

  private isCurrentFetch(abortController: AbortController, generation: number): boolean {
    return generation === this.connectionGeneration && this.abortController === abortController;
  }

  private closeActiveConnection(): void {
    if (this.eventSource) {
      this.closeEventSource(this.eventSource);
      this.eventSource = null;
    }
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  private closeEventSource(eventSource: EventSource): void {
    eventSource.onopen = null;
    eventSource.onmessage = null;
    eventSource.onerror = null;
    eventSource.close();
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectWaitResolve?.();
    this.reconnectWaitResolve = null;
  }

  private waitForReconnect(delay: number): Promise<void> {
    this.clearReconnectTimer();
    return new Promise((resolve) => {
      this.reconnectWaitResolve = resolve;
      this.reconnectTimer = setTimeout(() => {
        this.reconnectTimer = null;
        this.reconnectWaitResolve = null;
        resolve();
      }, delay);
    });
  }

  /**
   * Subscribe to events
   */
  public on<T = unknown>(event: string, listener: EventListener<T>): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(listener as EventListener<unknown>);

    // Return unsubscribe function
    return () => {
      this.listeners.get(event)?.delete(listener as EventListener<unknown>);
    };
  }

  /**
   * Emit event
   */
  private emit(event: string, data: unknown): void {
    const listeners = this.listeners.get(event);
    if (listeners) {
      listeners.forEach((listener) => {
        try {
          listener(data);
        } catch (e) {
          console.error(`Error in ${event} listener:`, e);
        }
      });
    }
  }

  /**
   * Disconnect from SSE
   */
  public disconnect(): void {
    this.connectionGeneration++;
    this.clearReconnectTimer();
    this.closeActiveConnection();
    this.parser.reset();
    this.reconnectAttempts = 0;
  }

  /**
   * Send a message to the server via POST and handle SSE response
   */
  public async sendMessage(
    message: string,
    customData?: Record<string, unknown>,
    options?: { headers?: Record<string, string>; signal?: AbortSignal }
  ): Promise<void> {
    if (!this.url) {
      throw new Error('Not connected to SSE endpoint');
    }

    try {
      const response = await fetch(this.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        body: JSON.stringify({
          message,
          ...customData,
        }),
        signal: options?.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Read the SSE stream from POST response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const parser = new SSEStreamParser();

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        for (const payload of parser.push(chunk)) {
          this.emitMessage(this.payloadToMessage(payload));
        }
      }
    } catch (error) {
      console.error('Error sending message:', error);
      this.handleError(error);
      throw error;
    }
  }

  /**
   * Destroy and cleanup
   */
  public destroy(): void {
    this.disconnect();
    this.listeners.clear();
  }
}
