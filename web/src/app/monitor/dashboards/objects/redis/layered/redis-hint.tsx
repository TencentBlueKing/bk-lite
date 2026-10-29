'use client';

import type { ReactNode } from 'react';
import { ProInfoHint } from '../../host/layered/pro-chrome';

export interface HintSegment {
  lead: string;
  body: string;
  /** 缺省按标题是否含汉字选择全角或半角冒号。等号档拆开后不再画出等号。 */
  sep?: '：' | ':' | '＝' | '=';
}

export interface HintGroup {
  title?: string;
  segments?: readonly HintSegment[];
  lines?: readonly string[];
  /** 整句不换行。无采样说明里的 0 不能单独掉到下一行。 */
  locked?: readonly string[];
}

/** 指标名单独成行。英文卡名比四字档名长，上限放宽到整段卡名仍能拆开。 */
const LEAD_LIMIT = 32;

const sepFor = (lead: string, sep?: HintSegment['sep']): string => {
  if (sep === ':' || sep === '=') return ': ';
  if (sep === '：' || sep === '＝') return '：';
  return /[\u3400-\u9fff]/.test(lead) ? '：' : ': ';
};

const equalsSegment = (line: string): HintSegment | null => {
  const full = line.indexOf('＝');
  if (full >= 2 && full <= LEAD_LIMIT) {
    const lead = line.slice(0, full).trim();
    const body = line.slice(full + 1).trim();
    if (lead && body) return { lead, body, sep: '＝' };
  }
  const ascii = line.match(new RegExp(`^(.{2,${LEAD_LIMIT}}?)\\s=\\s(.+)$`));
  if (!ascii) return null;
  const lead = ascii[1].trim();
  const body = ascii[2].trim();
  if (!lead || !body || lead.length > LEAD_LIMIT) return null;
  return { lead, body, sep: '=' };
};

/** 把已有「标题：正文」或「档名＝定义」拆成条目。拆不开时保持整句。 */
export function colonSegment(line: string): HintSegment | null {
  const equals = equalsSegment(line);
  if (equals) return equals;
  const full = line.indexOf('：');
  const ascii = line.indexOf(':');
  const useFull = full > 0 && (ascii < 0 || full < ascii);
  const at = useFull ? full : ascii;
  if (at < 2 || at > LEAD_LIMIT) return null;
  const lead = line.slice(0, at).trim();
  const body = line.slice(at + 1).trim();
  if (!lead || !body) return null;
  return { lead, body, sep: useFull ? '：' : ':' };
}

/** 档名单独一行加粗，释义在下，常规字重。等号不出现在气泡里。 */
function segmentNode(item: HintSegment) {
  return (
    <>
      <strong className="block text-[13px] font-bold leading-[1.55] text-[var(--color-text-1)]">{item.lead}</strong>
      <span className="mt-1 block font-normal">{item.body}</span>
    </>
  );
}

interface HintRow {
  node: ReactNode;
  nowrap?: boolean;
}

function lineRow(line: string, nowrap = false): HintRow {
  const split = colonSegment(line);
  return { node: split ? segmentNode(split) : line, nowrap };
}

function rowsOf(group: HintGroup): HintRow[] {
  const rows: HintRow[] = [];
  (group.segments ?? []).forEach((item) => {
    rows.push({ node: segmentNode(item) });
  });
  (group.lines ?? []).forEach((line) => {
    rows.push(lineRow(line));
  });
  (group.locked ?? []).forEach((line) => {
    rows.push(lineRow(line, true));
  });
  return rows;
}

function ariaOf(groups: readonly HintGroup[]) {
  return groups.flatMap((group) => {
    const bits: string[] = [];
    if (group.title) bits.push(group.title);
    (group.segments ?? []).forEach((item) => {
      bits.push(`${item.lead}${sepFor(item.lead, item.sep)}${item.body}`);
    });
    (group.lines ?? []).forEach((line) => bits.push(line));
    (group.locked ?? []).forEach((line) => bits.push(line));
    return bits;
  }).join(' ');
}

/** 浅色分段说明。可见文案按条目换行，不拼成一段。 */
export function RedisHint({
  kind,
  groups,
  segments,
  lines,
  locked
}: {
  kind: string;
  groups?: readonly HintGroup[];
  segments?: readonly HintSegment[];
  lines?: readonly string[];
  locked?: readonly string[];
}) {
  const resolved = (groups?.length ? groups : [{ segments, lines, locked }]).filter((group) => (
    Boolean(group.title)
    || Boolean(group.segments?.length)
    || Boolean(group.lines?.length)
    || Boolean(group.locked?.length)
  ));
  if (!resolved.length) return null;
  return (
    <ProInfoHint
      kind={kind}
      label={ariaOf(resolved)}
      content={(
        <div className="max-w-[380px] text-[13px] font-normal leading-[1.55] text-[var(--color-text-2)]">
          {resolved.map((group, groupIndex) => {
            const rows = rowsOf(group);
            return (
              <div key={group.title ?? groupIndex} className={groupIndex > 0 ? 'mt-3' : undefined}>
                {group.title ? (
                  <p className="m-0 text-[13px] font-bold leading-[1.55] text-[var(--color-text-1)]">
                    {group.title}
                  </p>
                ) : null}
                {rows.map((row, index) => (
                  <p
                    key={index}
                    className={[
                      index === 0 ? (group.title ? 'm-0 mt-1' : 'm-0') : 'm-0 mt-3',
                      row.nowrap ? 'whitespace-nowrap' : ''
                    ].filter(Boolean).join(' ')}
                  >
                    {row.node}
                  </p>
                ))}
              </div>
            );
          })}
        </div>
      )}
    />
  );
}

/** 图表标题上的字符串说明改成浅色分段，不再走深色气泡。 */
export function redisTextHint(kind: string, value: string) {
  const parts = value.split('\n').map((item) => item.trim()).filter(Boolean);
  if (!parts.length) return null;
  return <RedisHint kind={kind} lines={parts} />;
}
