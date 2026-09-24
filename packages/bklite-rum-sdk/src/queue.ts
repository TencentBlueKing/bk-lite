export class TransportQueueFullError extends Error {
  constructor() {
    super('Faro transport queue is full');
    this.name = 'TransportQueueFullError';
  }
}

export class TransportQueueDroppedError extends Error {
  constructor() {
    super('Faro transport queue dropped replaceable work');
    this.name = 'TransportQueueDroppedError';
  }
}

export interface QueueLimits {
  maxInFlight: number;
  maxQueuedItems: number;
  maxQueuedBytes: number;
}

export interface QueueWeight {
  bytes: number;
  droppable?: boolean;
  items: number;
}

interface QueueEntry extends Omit<QueueWeight, 'droppable'> {
  droppable: boolean;
  reject: (reason?: unknown) => void;
  resolve: () => void;
  task: () => Promise<void>;
}

/**
 * A browser-only bounded work queue. The byte/item limits apply to waiting
 * work; active requests are governed independently by maxInFlight.
 */
export class BoundedConcurrentQueue {
  private inFlight = 0;
  private queuedBytes = 0;
  private queuedItems = 0;
  private readonly waiting: QueueEntry[] = [];

  constructor(
    private readonly limits: QueueLimits,
    private readonly onDrop?: () => void,
  ) {
    for (const [name, value] of Object.entries(limits)) {
      if (!Number.isInteger(value) || value < 1) {
        throw new RangeError(`${name} must be a positive integer`);
      }
    }
  }

  enqueue(task: () => Promise<void>, weight: QueueWeight): Promise<void> {
    if (
      !Number.isInteger(weight.items) ||
      weight.items < 1 ||
      !Number.isInteger(weight.bytes) ||
      weight.bytes < 0
    ) {
      return Promise.reject(new RangeError('queue weight is invalid'));
    }

    if (this.inFlight >= this.limits.maxInFlight) {
      if (!this.makeRoom(weight)) {
        return Promise.reject(new TransportQueueFullError());
      }
    }

    const result = new Promise<void>((resolve, reject) => {
      const entry = {
        ...weight,
        droppable: weight.droppable ?? false,
        reject,
        resolve,
        task,
      };
      if (this.inFlight < this.limits.maxInFlight) {
        this.start(entry);
        return;
      }
      this.waiting.push(entry);
      this.queuedItems += entry.items;
      this.queuedBytes += entry.bytes;
    });

    return result;
  }

  snapshot(): { inFlight: number; queuedBytes: number; queuedItems: number } {
    return {
      inFlight: this.inFlight,
      queuedBytes: this.queuedBytes,
      queuedItems: this.queuedItems,
    };
  }

  private start(entry: QueueEntry): void {
    this.inFlight += 1;
    let running: Promise<void>;
    try {
      running = Promise.resolve(entry.task());
    } catch (error) {
      running = Promise.reject(error);
    }

    void running.then(entry.resolve, entry.reject).finally(() => {
      this.inFlight -= 1;
      this.pump();
    });
  }

  private makeRoom(weight: QueueWeight): boolean {
    const overLimit = () =>
      this.queuedItems + weight.items > this.limits.maxQueuedItems ||
      this.queuedBytes + weight.bytes > this.limits.maxQueuedBytes;

    while (overLimit()) {
      const index = this.waiting.findIndex((entry) => entry.droppable);
      if (index < 0) return false;
      const [dropped] = this.waiting.splice(index, 1);
      if (!dropped) return false;
      this.queuedItems -= dropped.items;
      this.queuedBytes -= dropped.bytes;
      dropped.reject(new TransportQueueDroppedError());
      this.onDrop?.();
    }
    return true;
  }

  private pump(): void {
    while (this.inFlight < this.limits.maxInFlight) {
      const entry = this.waiting.shift();
      if (!entry) return;
      this.queuedItems -= entry.items;
      this.queuedBytes -= entry.bytes;
      this.start(entry);
    }
  }
}
