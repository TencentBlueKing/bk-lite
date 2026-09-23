import {
  TransportQueueDroppedError as TransportQueueDroppedErrorValue,
  TransportQueueFullError as TransportQueueFullErrorValue,
} from '../src/queue.ts';
import {
  FARO_REPLAY_EVENT as FARO_REPLAY_EVENT_VALUE,
  FARO_REPLAY_RESUMED_EVENT as FARO_REPLAY_RESUMED_EVENT_VALUE,
  FARO_REPLAY_STARTED_EVENT as FARO_REPLAY_STARTED_EVENT_VALUE,
} from '../src/replay.ts';
import { sanitizeReplayEvent as sanitizeReplayEventValue } from '../src/replay-privacy.ts';
import { TransportRequestError as TransportRequestErrorValue } from '../src/retry.ts';
import { CoreRumTransport as CoreRumTransportValue } from '../src/transport.ts';

export const CoreRumTransport = CoreRumTransportValue;
export const FARO_REPLAY_EVENT = FARO_REPLAY_EVENT_VALUE;
export const FARO_REPLAY_RESUMED_EVENT = FARO_REPLAY_RESUMED_EVENT_VALUE;
export const FARO_REPLAY_STARTED_EVENT = FARO_REPLAY_STARTED_EVENT_VALUE;
export const sanitizeReplayEvent = sanitizeReplayEventValue;
export const TransportQueueDroppedError = TransportQueueDroppedErrorValue;
export const TransportQueueFullError = TransportQueueFullErrorValue;
export const TransportRequestError = TransportRequestErrorValue;
