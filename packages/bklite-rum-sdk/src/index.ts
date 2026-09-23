import { TransportQueueDroppedError, TransportQueueFullError } from './queue';
import {
  FARO_REPLAY_EVENT,
  FARO_REPLAY_RESUMED_EVENT,
  FARO_REPLAY_STARTED_EVENT,
} from './replay';
import { sanitizeReplayEvent } from './replay-privacy';
import { TransportRequestError } from './retry';
import { CoreRumTransport } from './transport';

export {
  CoreRumTransport,
  FARO_REPLAY_EVENT,
  FARO_REPLAY_RESUMED_EVENT,
  FARO_REPLAY_STARTED_EVENT,
  sanitizeReplayEvent,
  TransportQueueDroppedError,
  TransportQueueFullError,
  TransportRequestError,
};
export type {
  CoreRumDebugEvent,
  CoreRumTransportOptions,
} from './transport';
