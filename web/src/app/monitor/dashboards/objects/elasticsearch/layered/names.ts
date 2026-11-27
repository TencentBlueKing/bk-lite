/** 同一张卡里，节点名有共同的「以 - 结尾的前缀」时只留后半段。 */
export const foldNodeNames = (names: readonly string[]): Map<string, string> => {
  const unique = [...new Set(names.map((name) => name.trim()).filter(Boolean))];
  const folded = new Map(unique.map((name) => [name, name]));
  if (unique.length < 2) return folded;
  let prefix = unique[0];
  unique.slice(1).forEach((name) => {
    let index = 0;
    const limit = Math.min(prefix.length, name.length);
    while (index < limit && prefix[index] === name[index]) index += 1;
    prefix = prefix.slice(0, index);
  });
  const dash = prefix.lastIndexOf('-');
  if (dash < 0) return folded;
  const cut = prefix.slice(0, dash + 1);
  if (!cut.endsWith('-')) return folded;
  if (unique.some((name) => !name.startsWith(cut) || name.length === cut.length)) return folded;
  unique.forEach((name) => folded.set(name, name.slice(cut.length)));
  return folded;
};

export const clockText = (seconds: number | null | undefined, withSeconds = false): string => {
  if (seconds == null || !Number.isFinite(seconds)) return '';
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (value: number) => String(value).padStart(2, '0');
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  if (!withSeconds) return `${hours}:${minutes}`;
  return `${hours}:${minutes}:${pad(date.getSeconds())}`;
};
