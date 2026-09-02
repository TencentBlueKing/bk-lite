export const dashboardQueryCapabilityId = (template: string): string => {
  let hash = 2166136261;
  for (const byte of new TextEncoder().encode(template)) {
    hash ^= byte;
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return `dashboard:v1:${hash.toString(16).padStart(8, '0')}`;
};
