/** A token proving ownership of the stream that may update Chat state. */
export interface StreamLease {
  readonly id: number;
  readonly signal?: AbortSignal;
}

/** The ReadableStream cleanup surface owned by StreamLifecycle. */
export interface StreamReader {
  read(): Promise<ReadableStreamReadResult<Uint8Array>>;
  cancel(reason?: unknown): Promise<void>;
  releaseLock(): void;
}

interface ActiveStream extends StreamLease {
  controller: AbortController | null;
  reader: StreamReader | null;
}

type AbortControllerFactory = () => AbortController | null;
/** A finite reason recorded when an owned stream is cancelled. */
export type StreamCancelReason =
  | 'replaced-by-new-stream'
  | 'stale-stream'
  | 'component-unmounted'
  | 'user-stopped'
  | 'session-cleared';

const createAbortController: AbortControllerFactory = () =>
  typeof AbortController === 'undefined' ? null : new AbortController();

/** Returns whether an unknown failure represents expected stream cancellation. */
export function isAbortError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    error.name === 'AbortError'
  );
}

/** Converts an unknown stream failure into the public onError contract. */
export function toError(error: unknown): Error {
  if (error instanceof Error) {
    return error;
  }
  return new Error(typeof error === 'string' ? error : 'Unknown stream error');
}

/**
 * Owns the single stream that may mutate a Chat instance.
 *
 * AbortController releases the network request when the runtime supports it.
 * The lease check remains the correctness boundary: stale streams cannot write
 * even when an older fetch implementation ignores AbortSignal.
 */
export class StreamLifecycle {
  private active: ActiveStream | null = null;
  private mounted = false;
  private nextId = 0;

  /** Creates a lifecycle with an optional AbortController compatibility seam. */
  public constructor(
    private readonly abortControllerFactory: AbortControllerFactory = createAbortController
  ) {}

  /** Enables stream creation for the mounted Chat instance. */
  public mount(): void {
    this.mounted = true;
  }

  /** Starts a new lease and cancels any stream that previously owned state. */
  public begin(): StreamLease | null {
    if (!this.mounted) {
      return null;
    }

    void this.cancel('replaced-by-new-stream');
    const controller = this.abortControllerFactory();
    const stream: ActiveStream = {
      id: ++this.nextId,
      signal: controller?.signal,
      controller,
      reader: null,
    };
    this.active = stream;
    return stream;
  }

  /** Returns true only for the mounted instance's current stream lease. */
  public isActive(stream: StreamLease): boolean {
    return this.mounted && this.active === stream;
  }

  /** Attaches the response reader, cleaning it immediately if the lease is stale. */
  public attachReader(stream: StreamLease, reader: StreamReader): boolean {
    const active = this.active;
    if (!this.mounted || active !== stream) {
      void this.cancelReader(reader, 'stale-stream');
      return false;
    }

    active.reader = reader;
    return true;
  }

  /**
   * Completes only the current lease. A stale stream cannot reset loading
   * state owned by the stream that replaced it.
   */
  public complete(stream: StreamLease): boolean {
    const active = this.active;
    if (!this.mounted || active !== stream) {
      return false;
    }

    const reader = active.reader;
    active.reader = null;
    this.active = null;
    this.releaseReader(reader);
    return true;
  }

  /**
   * Deactivates synchronously, then finishes reader cleanup asynchronously.
   * Callers do not need to await this method to stop stale state writes.
   */
  public cancel(reason: StreamCancelReason): Promise<void> {
    const stream = this.active;
    if (!stream) {
      return Promise.resolve();
    }

    this.active = null;
    stream.controller?.abort();
    const reader = stream.reader;
    stream.reader = null;
    return reader ? this.cancelReader(reader, reason) : Promise.resolve();
  }

  /** Permanently deactivates the current mount and cancels its active stream. */
  public dispose(): Promise<void> {
    this.mounted = false;
    return this.cancel('component-unmounted');
  }

  private async cancelReader(
    reader: StreamReader,
    reason: StreamCancelReason
  ): Promise<void> {
    try {
      await reader.cancel(reason);
    } catch {
      // Fetch abort may already have errored the reader; releasing ownership is
      // still sufficient and cleanup must never surface as a user-facing error.
    } finally {
      this.releaseReader(reader);
    }
  }

  private releaseReader(reader: StreamReader | null): void {
    if (!reader) {
      return;
    }

    try {
      reader.releaseLock();
    } catch {
      // A runtime may release an errored reader automatically.
    }
  }
}

/** Callbacks and request factory for one fully owned streaming request. */
export interface OwnedStreamRun {
  lifecycle: StreamLifecycle;
  stream: StreamLease;
  request: (signal?: AbortSignal) => Promise<Response>;
  onChunk: (chunk: Uint8Array) => void;
  onError: (error: Error) => void;
  onComplete: () => void;
}

/**
 * Runs fetch and reader consumption under one lease.
 *
 * Only the current lease may deliver chunks, surface errors, or complete UI
 * state. Cancellation and stale-response reader cleanup are owned centrally.
 */
export async function runOwnedStream({
  lifecycle,
  stream,
  request,
  onChunk,
  onError,
  onComplete,
}: OwnedStreamRun): Promise<void> {
  try {
    const response = await request(stream.signal);
    if (!response.ok || !response.body) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    if (!lifecycle.attachReader(stream, reader)) {
      return;
    }

    while (lifecycle.isActive(stream)) {
      const { done, value } = await reader.read();
      if (done || !lifecycle.isActive(stream)) {
        break;
      }
      onChunk(value);
    }
  } catch (error: unknown) {
    if (!isAbortError(error) && lifecycle.isActive(stream)) {
      onError(toError(error));
    }
  } finally {
    if (lifecycle.complete(stream)) {
      onComplete();
    }
  }
}
