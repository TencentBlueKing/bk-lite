declare module '@grafana/rrweb' {
  export interface eventWithTime {
    type?: number;
    data?: Record<string, unknown>;
    timestamp?: number;
  }

  export class Replayer {
    constructor(events: unknown[], options?: Record<string, unknown>);
    iframe: HTMLIFrameElement;
    wrapper: HTMLElement;
    play(timeOffset?: number): void;
    pause(timeOffset?: number): void;
    getMetaData(): { totalTime: number };
    getCurrentTime(): number;
    setConfig(config: Record<string, unknown>): void;
    addEventListener(type: string, handler: (...args: unknown[]) => void): void;
    destroy(): void;
  }
}

declare module '@grafana/rrweb-replay' {
  export { Replayer } from '@grafana/rrweb';
}

declare module '@grafana/rrweb-replay/dist/style.css';
