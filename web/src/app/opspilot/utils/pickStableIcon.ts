/** Stable icon pick from a pool — same entity always same icon, consecutive ids won't A/B alternate. */
export function pickStableIcon(
  seed: string | number,
  icons: string[],
  extraSeed?: string | number | null
): string | undefined {
  if (!icons.length) return undefined;

  const raw = `${seed}\0${extraSeed ?? ''}`;
  // FNV-1a 32-bit — mixes better than char-code fold for short numeric ids
  let hash = 2166136261;
  for (let i = 0; i < raw.length; i += 1) {
    hash ^= raw.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return icons[(hash >>> 0) % icons.length];
}
