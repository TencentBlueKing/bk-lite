import {
  buildSkillSessionDeletePayload,
  shouldOfferKeepMemory,
} from '../skillMemoryUi';

describe('skillMemoryUi', () => {
  it('hides keep-memory unless pending rounds exist', () => {
    expect(shouldOfferKeepMemory(0)).toBe(false);
    expect(shouldOfferKeepMemory(undefined)).toBe(false);
    expect(shouldOfferKeepMemory(2)).toBe(true);
  });

  it('posts keep_memory with the session id', () => {
    expect(buildSkillSessionDeletePayload('sid-1', true)).toEqual({
      session_id: 'sid-1',
      keep_memory: true,
    });
    expect(buildSkillSessionDeletePayload('sid-2')).toEqual({
      session_id: 'sid-2',
      keep_memory: false,
    });
  });
});
