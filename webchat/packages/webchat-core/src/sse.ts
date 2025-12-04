import { Message, EventListener, MessageEvent } from './types';

/**
 * SSEHandler: Handles Server-Sent Events for streaming chat responses
 */
export class SSEHandler {
  private eventSource: EventSource | null = null;
  private abortController: AbortController | null = null;
  private listeners: Map<string, Set<EventListener<any>>> = new Map();
  private messageBuffer: string = '';
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number;
  private reconnectDelay: number;
  private url: string = '';

  constructor(maxReconnectAttempts: number = 5, reconnectDelay: number = 1000) {
    this.maxReconnectAttempts = maxReconnectAttempts;
    this.reconnectDelay = reconnectDelay;
  }

  /**
   * Connect to SSE endpoint
   */
  public connect(url: string, headers?: Record<string, string>): Promise<void> {
    this.url = url;
    return new Promise((resolve, reject) => {
      try {
        // Note: EventSource doesn't support custom headers directly
        // For custom headers, use fetch with ReadableStream
        if (headers) {
          this.connectWithFetch(url, headers).then(resolve).catch(reject);
          return;
        }

        this.eventSource = new EventSource(url);

        this.eventSource.onopen = () => {
          console.log('SSE connection opened');
          this.reconnectAttempts = 0;
          this.emit('open', { timestamp: Date.now() });
          resolve();
        };

        this.eventSource.onmessage = (event) => {
          this.handleMessage(event.data);
        };

        this.eventSource.onerror = (error) => {
          console.error('SSE error:', error);
          this.handleError(error);
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnect(url, headers);
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
    headers: Record<string, string>
  ): Promise<void> {
    try {
      this.abortController = new AbortController();

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'text/event-stream',
          ...headers,
        },
        signal: this.abortController.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      this.reconnectAttempts = 0;
      this.emit('open', { timestamp: Date.now() });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        this.processChunk(chunk);
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        console.error('Fetch SSE error:', error);
        this.handleError(error);
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          await this.sleep(this.reconnectDelay);
          this.reconnectAttempts++;
          this.connectWithFetch(url, headers);
        }
      }
    }
  }

  /**
   * Process incoming chunk
   */
  private processChunk(chunk: string): void {
    this.messageBuffer += chunk;
    const lines = this.messageBuffer.split('\n');

    // Keep the last incomplete line in buffer
    this.messageBuffer = lines[lines.length - 1];

    for (let i = 0; i < lines.length - 1; i++) {
      const line = lines[i].trim();
      if (line && !line.startsWith(':')) {
        this.handleMessage(line);
      }
    }
  }

  /**
   * Handle incoming SSE message
   */
  private handleMessage(line: string): void {
    try {
      const message = this.parseSSEMessage(line);
      this.emit('message', { message, timestamp: Date.now() } as MessageEvent);
    } catch (error) {
      console.error('Error handling SSE message:', error);
    }
  }

  /**
   * Parse SSE message format
   */
  private parseSSEMessage(line: string): Message {
    let data = line;

    if (line.startsWith('data: ')) {
      data = line.substring(6);
    }

    try {
      const json = JSON.parse(data);
      return {
        id: json.id || `msg_${Date.now()}`,
        type: json.type || 'text',
        content: json.content || data,
        sender: json.sender || 'bot',
        timestamp: json.timestamp || Date.now(),
        metadata: json.metadata,
      };
    } catch {
      // If not JSON, treat as plain text
      return {
        id: `msg_${Date.now()}`,
        type: 'text',
        content: data,
        sender: 'bot',
        timestamp: Date.now(),
      };
    }
  }

  /**
   * Handle connection error
   */
  private handleError(error: any): void {
    this.emit('error', { error, timestamp: Date.now() });
  }

  /**
   * Reconnect to SSE
   */
  private async reconnect(url: string, headers?: Record<string, string>): Promise<void> {
    this.reconnectAttempts++;
    console.log(
      `Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`
    );

    await this.sleep(this.reconnectDelay * this.reconnectAttempts);
    this.connect(url, headers).catch((error) => {
      console.error('Reconnection failed:', error);
    });
  }

  /**
   * Subscribe to events
   */
  public on(event: string, listener: EventListener<any>): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(listener);

    // Return unsubscribe function
    return () => {
      this.listeners.get(event)?.delete(listener);
    };
  }

  /**
   * Emit event
   */
  private emit(event: string, data: any): void {
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
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
    this.messageBuffer = '';
    this.reconnectAttempts = 0;
  }

  /**
   * Sleep utility
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Send a message to the server via POST and handle SSE response
   */
  public async sendMessage(message: string, customData?: Record<string, any>): Promise<void> {
    if (!this.url) {
      throw new Error('Not connected to SSE endpoint');
    }

    try {
      const response = await fetch(this.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message,
          ...customData,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      // Read the SSE stream from POST response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        this.processChunk(chunk);
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
