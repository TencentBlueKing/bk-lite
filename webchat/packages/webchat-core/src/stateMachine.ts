import { ChatState, StateChangeEvent, EventListener } from './types';

/**
 * StateMachine: Manages chat state transitions
 */
export class StateMachine {
  private state: ChatState = 'idle';
  private listeners: Map<string, Set<EventListener<StateChangeEvent>>> = new Map();

  constructor(initialState: ChatState = 'idle') {
    this.state = initialState;
  }

  /**
   * Get current state
   */
  public getState(): ChatState {
    return this.state;
  }

  /**
   * Check if in specific state
   */
  public isState(state: ChatState): boolean {
    return this.state === state;
  }

  /**
   * Transition to new state
   */
  public transition(to: ChatState): boolean {
    if (!this.isValidTransition(this.state, to)) {
      console.warn(`Invalid transition from ${this.state} to ${to}`);
      return false;
    }

    const from = this.state;
    this.state = to;
    this.emit(from, to);
    return true;
  }

  /**
   * Move into chatting through the state machine's legal connection states.
   */
  public transitionToChatting(): boolean {
    const pathByState: Partial<Record<ChatState, ChatState[]>> = {
      idle: ['connecting', 'connected', 'chatting'],
      connecting: ['connected', 'chatting'],
      connected: ['chatting'],
      chatting: [],
      closed: ['idle', 'connecting', 'connected', 'chatting'],
      error: ['idle', 'connecting', 'connected', 'chatting'],
    };

    const path = pathByState[this.state];
    if (!path) {
      return false;
    }

    return path.every((state) => this.transition(state));
  }

  /**
   * Subscribe to state changes
   */
  public on(listener: EventListener<StateChangeEvent>): () => void {
    const key = 'stateChange';
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key)!.add(listener);

    // Return unsubscribe function
    return () => {
      this.listeners.get(key)?.delete(listener);
    };
  }

  /**
   * Validate state transitions
   */
  private isValidTransition(from: ChatState, to: ChatState): boolean {
    const validTransitions: Record<ChatState, ChatState[]> = {
      idle: ['connecting', 'closed'],
      connecting: ['connected', 'error', 'closed'],
      connected: ['chatting', 'closed', 'error'],
      chatting: ['connected', 'closed', 'error'],
      error: ['connecting', 'closed', 'idle'],
      closed: ['idle', 'connecting'],
    };

    return validTransitions[from]?.includes(to) || false;
  }

  /**
   * Emit state change event
   */
  private emit(from: ChatState, to: ChatState): void {
    const event: StateChangeEvent = {
      from,
      to,
      timestamp: Date.now(),
    };

    const key = 'stateChange';
    const listeners = this.listeners.get(key);
    if (listeners) {
      listeners.forEach((listener) => {
        try {
          listener(event);
        } catch (e) {
          console.error('Error in state change listener:', e);
        }
      });
    }
  }

  /**
   * Clear all listeners
   */
  public destroy(): void {
    this.listeners.clear();
  }
}
