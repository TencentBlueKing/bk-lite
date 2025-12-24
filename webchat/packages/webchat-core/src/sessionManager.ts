import { ChatSession, Message, WebChatConfig } from './types';

/**
 * SessionManager: Manages chat sessions and persistence
 */
export class SessionManager {
  private session: ChatSession | null = null;
  private config: WebChatConfig;
  private storageKey: string;

  constructor(config: WebChatConfig = {}) {
    this.config = config;
    this.storageKey = config.storageKey || '@webchat/session';
  }

  /**
   * Initialize or restore a session
   */
  public initSession(userId?: string): ChatSession {
    if (this.session) {
      return this.session;
    }

    // Try to restore from storage
    if (this.config.enableStorage) {
      const restored = this.restoreFromStorage();
      if (restored) {
        this.session = restored;
        return this.session;
      }
    }

    // Create new session
    const session: ChatSession = {
      sessionId: this.generateSessionId(),
      userId: userId || undefined,
      messages: [],
      startTime: Date.now(),
      lastActivityTime: Date.now(),
      customData: this.config.customData || {},
    };

    this.session = session;
    this.saveToStorage();
    return session;
  }

  /**
   * Get current session
   */
  public getSession(): ChatSession | null {
    return this.session;
  }

  /**
   * Add a message to the session
   */
  public addMessage(message: Message): void {
    if (!this.session) {
      throw new Error('Session not initialized');
    }
    this.session.messages.push(message);
    this.session.lastActivityTime = Date.now();
    this.saveToStorage();
  }

  /**
   * Get all messages
   */
  public getMessages(): Message[] {
    return this.session?.messages || [];
  }

  /**
   * Clear session
   */
  public clearSession(): void {
    this.session = null;
    if (this.config.enableStorage && typeof localStorage !== 'undefined') {
      try {
        localStorage.removeItem(this.storageKey);
      } catch (e) {
        console.warn('Failed to clear session from storage:', e);
      }
    }
  }

  /**
   * Manually save current session to storage
   */
  public saveSession(): void {
    this.saveToStorage();
  }

  /**
   * Save session to storage
   */
  private saveToStorage(): void {
    if (!this.config.enableStorage || !this.session || typeof localStorage === 'undefined') {
      return;
    }

    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this.session));
    } catch (e) {
      console.warn('Failed to save session to storage:', e);
    }
  }

  /**
   * Restore session from storage
   */
  private restoreFromStorage(): ChatSession | null {
    if (typeof localStorage === 'undefined') {
      return null;
    }
    try {
      const stored = localStorage.getItem(this.storageKey);
      if (stored) {
        const session = JSON.parse(stored) as ChatSession;
        // Only restore if session is recent (less than 24 hours old)
        if (Date.now() - session.lastActivityTime < 24 * 60 * 60 * 1000) {
          return session;
        }
      }
    } catch (e) {
      console.warn('Failed to restore session from storage:', e);
    }
    return null;
  }

  /**
   * Generate unique session ID
   */
  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}
