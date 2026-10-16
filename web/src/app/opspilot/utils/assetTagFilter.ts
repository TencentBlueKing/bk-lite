export interface TagSource {
  systemTags: string[];
  userTags: string[];
}

export interface TagChip {
  value: string;
  label: string;
  matchValues: string[];
}

export interface AssetFilterState {
  selectedTags: string[];
  keyword: string;
}

export function normalizeUserTags(raw: Array<string | null | undefined> | undefined): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of raw || []) {
    const text = String(item ?? '').trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    result.push(text);
  }
  return result;
}

export function collectTagChips(
  items: TagSource[],
  labelFor: (value: string, kind: 'system' | 'user') => string,
): TagChip[] {
  const chips: TagChip[] = [];

  const findChip = (token: string) => chips.find((chip) => chip.value === token || chip.label === token || chip.matchValues.includes(token));

  for (const item of items) {
    for (const id of item.systemTags || []) {
      if (!id || findChip(id)) continue;
      const label = labelFor(id, 'system') || id;
      const matchValues = label === id ? [id] : [id, label];
      chips.push({ value: id, label, matchValues });
    }
  }

  for (const item of items) {
    for (const word of item.userTags || []) {
      if (!word) continue;
      const collided = findChip(word);
      if (collided) {
        if (!collided.matchValues.includes(word)) collided.matchValues.push(word);
        continue;
      }
      chips.push({
        value: word,
        label: labelFor(word, 'user') || word,
        matchValues: [word],
      });
    }
  }

  return chips;
}

export function matchesTagSelection(item: TagSource, selected: string[], chips: TagChip[]): boolean {
  if (!selected.length) return true;
  const system = new Set(item.systemTags || []);
  const user = new Set(item.userTags || []);
  return selected.some((value) => {
    const chip = chips.find((candidate) => candidate.value === value);
    const tokens = chip ? chip.matchValues : [value];
    return tokens.some((token) => system.has(token) || user.has(token));
  });
}

export function matchesKeyword(name: string, description: string, keyword: string, extra = ''): boolean {
  const text = keyword.trim().toLowerCase();
  if (!text) return true;
  return [name, description, extra].some((part) => (part || '').toLowerCase().includes(text));
}

export function filterTaggedAssets<T>(
  items: T[],
  options: {
    selectedTags: string[];
    keyword: string;
    chips: TagChip[];
    systemTags: (item: T) => string[];
    userTags: (item: T) => string[];
    name: (item: T) => string;
    description: (item: T) => string;
    extraKeyword?: (item: T) => string;
  },
): T[] {
  return items.filter((item) => {
    const source = { systemTags: options.systemTags(item), userTags: options.userTags(item) };
    if (!matchesTagSelection(source, options.selectedTags, options.chips)) return false;
    return matchesKeyword(
      options.name(item),
      options.description(item),
      options.keyword,
      options.extraKeyword ? options.extraKeyword(item) : '',
    );
  });
}

export function clearAssetFilter(state: AssetFilterState): AssetFilterState {
  return { ...state, selectedTags: [], keyword: '' };
}
