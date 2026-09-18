import { describe, expect, it } from 'vitest';
import { channelOptionValue } from '../channelIdentity';

describe('channelOptionValue', () => {
  it('keeps Channel and IM channels with the same numeric id distinct', () => {
    expect(channelOptionValue({ id: 5, channel_type: 'email' })).toBe('email:5');
    expect(channelOptionValue({ id: 5, channel_type: 'im_notification' }))
      .toBe('im_notification:5');
  });
});
