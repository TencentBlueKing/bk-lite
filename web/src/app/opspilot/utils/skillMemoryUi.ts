export function shouldOfferKeepMemory(pendingRounds?: number | null): boolean {
  return (Number(pendingRounds) || 0) > 0;
}

export function buildSkillSessionDeletePayload(sessionId: string, keepMemory = false) {
  return { session_id: sessionId, keep_memory: keepMemory };
}
