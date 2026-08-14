export interface RuntimeRequestPriority {
  cause: number;
  visibility: number;
  distance: number;
  order: number;
}

interface RuntimeRequestConsumer<T> {
  consumerId: string;
  ownerId: string;
  priority: RuntimeRequestPriority;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
}

interface RuntimeRequestEntry<T = unknown> {
  physicalKey: string;
  state: 'queued' | 'started';
  priority: RuntimeRequestPriority;
  consumers: Map<string, RuntimeRequestConsumer<T>>;
  start: () => Promise<T>;
}

interface ScheduleRuntimeRequest<T> {
  consumerId: string;
  ownerId: string;
  physicalKey: string;
  priority: RuntimeRequestPriority;
  start: () => Promise<T>;
}

export class RuntimeRequestCancelledError extends Error {
  constructor() {
    super('Dashboard runtime request cancelled before physical start');
    this.name = 'RuntimeRequestCancelledError';
  }
}

const comparePriority = (
  left: RuntimeRequestPriority,
  right: RuntimeRequestPriority,
) => left.cause - right.cause
  || left.visibility - right.visibility
  || left.distance - right.distance
  || left.order - right.order;

const bestPriority = <T,>(entry: RuntimeRequestEntry<T>) =>
  Array.from(entry.consumers.values())
    .map((consumer) => consumer.priority)
    .sort(comparePriority)[0];

export class DashboardRuntimeScheduler {
  private readonly concurrency: number;
  private readonly entries = new Map<string, RuntimeRequestEntry>();
  private running = 0;
  private destroyed = false;

  constructor({ concurrency = 6 }: { concurrency?: number } = {}) {
    this.concurrency = Math.max(1, concurrency);
  }

  schedule<T>({
    consumerId,
    ownerId,
    physicalKey,
    priority,
    start,
  }: ScheduleRuntimeRequest<T>): Promise<T> {
    if (this.destroyed) {
      return Promise.reject(new RuntimeRequestCancelledError());
    }

    const existing = this.entries.get(physicalKey) as RuntimeRequestEntry<T> | undefined;
    return new Promise<T>((resolve, reject) => {
      const consumer: RuntimeRequestConsumer<T> = {
        consumerId,
        ownerId,
        priority,
        resolve,
        reject,
      };
      if (existing) {
        existing.consumers.set(consumerId, consumer);
        if (existing.state === 'queued') {
          existing.priority = bestPriority(existing);
          this.drain();
        }
        return;
      }

      const entry: RuntimeRequestEntry<T> = {
        physicalKey,
        state: 'queued',
        priority,
        consumers: new Map([[consumerId, consumer]]),
        start,
      };
      this.entries.set(physicalKey, entry as RuntimeRequestEntry);
      this.drain();
    });
  }

  cancelQueuedForOwner(ownerId: string): void {
    this.entries.forEach((entry, key) => {
      if (entry.state !== 'queued') return;
      entry.consumers.forEach((consumer, consumerId) => {
        if (consumer.ownerId !== ownerId) return;
        entry.consumers.delete(consumerId);
        consumer.reject(new RuntimeRequestCancelledError());
      });
      if (entry.consumers.size === 0) {
        this.entries.delete(key);
      } else {
        entry.priority = bestPriority(entry);
      }
    });
  }

  updateOwnerPriority(ownerId: string, priority: RuntimeRequestPriority): void {
    this.entries.forEach((entry) => {
      if (entry.state !== 'queued') return;
      entry.consumers.forEach((consumer) => {
        if (consumer.ownerId === ownerId) {
          consumer.priority = {
            ...priority,
            cause: consumer.priority.cause,
          };
        }
      });
      entry.priority = bestPriority(entry);
    });
    this.drain();
  }

  destroy(): void {
    if (this.destroyed) return;
    this.destroyed = true;
    this.entries.forEach((entry, key) => {
      if (entry.state !== 'queued') return;
      entry.consumers.forEach((consumer) => {
        consumer.reject(new RuntimeRequestCancelledError());
      });
      this.entries.delete(key);
    });
  }

  snapshot() {
    return {
      running: this.running,
      queued: Array.from(this.entries.values()).filter(
        (entry) => entry.state === 'queued',
      ).length,
      destroyed: this.destroyed,
    };
  }

  private drain(): void {
    while (!this.destroyed && this.running < this.concurrency) {
      const next = Array.from(this.entries.values())
        .filter((entry) => entry.state === 'queued')
        .sort((left, right) => comparePriority(left.priority, right.priority))[0];
      if (!next) return;
      this.startEntry(next);
    }
  }

  private startEntry(entry: RuntimeRequestEntry): void {
    entry.state = 'started';
    this.running += 1;
    let request: Promise<unknown>;
    try {
      request = entry.start();
    } catch (reason) {
      this.finishEntry(entry);
      entry.consumers.forEach((consumer) => consumer.reject(reason));
      return;
    }
    void Promise.resolve(request).then(
      (value) => {
        this.finishEntry(entry);
        entry.consumers.forEach((consumer) => consumer.resolve(value));
      },
      (reason) => {
        this.finishEntry(entry);
        entry.consumers.forEach((consumer) => consumer.reject(reason));
      },
    );
  }

  private finishEntry(entry: RuntimeRequestEntry): void {
    if (this.entries.get(entry.physicalKey) === entry) {
      this.entries.delete(entry.physicalKey);
    }
    this.running = Math.max(0, this.running - 1);
    this.drain();
  }
}
