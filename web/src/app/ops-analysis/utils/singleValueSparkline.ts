const hashSeed = (seedSource: string) => {
  let hash = 2166136261;
  for (let index = 0; index < seedSource.length; index += 1) {
    hash ^= seedSource.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
};

const createSeededRandom = (seedSource: string) => {
  let seed = hashSeed(seedSource) || 1;
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 0xffffffff;
  };
};

export const buildFallbackSparkline = (
  baseValue: number | null,
  baselineValue: number | null,
  seedSource: string,
): number[] => {
  const resolvedBase = Math.abs(baseValue ?? baselineValue ?? 100) || 100;
  const random = createSeededRandom(seedSource);
  const amplitudeRatio = 0.04 + random() * 0.03;
  const amplitude = Math.max(resolvedBase * amplitudeRatio, 6);
  const delta =
    baselineValue !== null && baseValue !== null ? baseValue - baselineValue : 0;
  const direction = delta === 0 ? 0 : delta > 0 ? 1 : -1;
  const relativeDelta =
    baselineValue !== null && baseValue !== null
      ? Math.abs(delta) / Math.max(Math.abs(baselineValue), 1)
      : 0;
  const trendSpan =
    direction === 0
      ? 0
      : amplitude * (1.5 + Math.min(relativeDelta, 1.5) * 1.8);
  const primaryFrequency = 2 + Math.round(random() * 2);
  const secondaryFrequency = 4 + Math.round(random() * 2);
  const tertiaryFrequency = 6 + Math.round(random() * 3);
  const primaryPhase = random() * Math.PI * 0.35;
  const secondaryPhase = random() * Math.PI * 0.45;
  const tertiaryPhase = random() * Math.PI * 0.55;
  const secondaryWeight = 0.18 + random() * 0.14;
  const tertiaryWeight = 0.08 + random() * 0.08;

  return Array.from({ length: 24 }, (_, index) => {
    const progress = index / 23;
    const envelope = Math.sin(progress * Math.PI);
    const primaryWave = Math.sin(
      progress * Math.PI * primaryFrequency + primaryPhase,
    );
    const secondaryWave = Math.sin(
      progress * Math.PI * secondaryFrequency + secondaryPhase,
    );
    const tertiaryWave = Math.sin(
      progress * Math.PI * tertiaryFrequency + tertiaryPhase,
    );
    const oscillation =
      envelope *
      amplitude *
      (0.55 * primaryWave +
        secondaryWeight * secondaryWave +
        tertiaryWeight * tertiaryWave);
    const trendBase = resolvedBase + (progress - 0.5) * trendSpan * direction;

    return trendBase + oscillation;
  });
};