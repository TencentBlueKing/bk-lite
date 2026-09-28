declare module '@grafana/rrweb' {
  export interface eventWithTime {
    type: number;
    data?: { width?: number; height?: number };
    timestamp?: number;
  }

  export class Replayer {
    iframe: HTMLIFrameElement;
    wrapper: HTMLElement;
    constructor(events: eventWithTime[], config?: Record<string, unknown>);
    play(timeOffset?: number): void;
    pause(timeOffset?: number): void;
    destroy(): void;
    getCurrentTime(): number;
    getMetaData(): { totalTime: number };
    setConfig(config: { speed?: number }): void;
  }
}

declare module '@grafana/rrweb-replay' {
  export { Replayer } from '@grafana/rrweb';
}

declare module '@grafana/rrweb-replay/dist/style.css';
