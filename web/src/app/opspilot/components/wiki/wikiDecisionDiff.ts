/** Knowledge-conflict sentence/paragraph diff for the decision center (frontend-only). */

export type DiffSegmentStatus = "equal" | "changed" | "added" | "removed";

export interface DiffSegment {
  text: string;
  status: DiffSegmentStatus;
}

export interface DiffHighlight {
  kind: "changed" | "added" | "removed";
  left?: string;
  right?: string;
}

export interface KnowledgeConflictDiff {
  leftSegments: DiffSegment[];
  rightSegments: DiffSegment[];
  highlights: DiffHighlight[];
  changeCount: number;
}

const normalizeKey = (text: string) => text.replace(/\s+/g, " ").trim();

const splitBlocks = (body: string): string[] => {
  const normalized = (body || "").replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  return normalized
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
};

const splitSentences = (block: string): string[] => {
  const result: string[] = [];
  for (const rawLine of block.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    if (
      /^#{1,6}\s/.test(line) ||
      /^[-*+]\s+/.test(line) ||
      /^\d+\.\s+/.test(line)
    ) {
      result.push(line);
      continue;
    }
    const parts = line.split(/(?<=[。！？.!?])\s+/);
    for (const part of parts) {
      const trimmed = part.trim();
      if (trimmed) result.push(trimmed);
    }
  }
  return result.length ? result : [block.trim()].filter(Boolean);
};

interface AlignRow {
  left?: string;
  right?: string;
  status: DiffSegmentStatus;
}

const lcsAlign = (left: string[], right: string[]): AlignRow[] => {
  const n = left.length;
  const m = right.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () =>
    Array(m + 1).fill(0),
  );
  for (let i = 1; i <= n; i += 1) {
    for (let j = 1; j <= m; j += 1) {
      if (normalizeKey(left[i - 1]) === normalizeKey(right[j - 1])) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  const ops: AlignRow[] = [];
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (
      i > 0 &&
      j > 0 &&
      normalizeKey(left[i - 1]) === normalizeKey(right[j - 1])
    ) {
      ops.push({ left: left[i - 1], right: right[j - 1], status: "equal" });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ right: right[j - 1], status: "added" });
      j -= 1;
    } else {
      ops.push({ left: left[i - 1], status: "removed" });
      i -= 1;
    }
  }
  ops.reverse();

  const merged: AlignRow[] = [];
  for (let index = 0; index < ops.length; index += 1) {
    const current = ops[index];
    const next = ops[index + 1];
    if (current.status === "removed" && next?.status === "added") {
      merged.push({
        left: current.left,
        right: next.right,
        status: "changed",
      });
      index += 1;
    } else {
      merged.push(current);
    }
  }
  return merged;
};

const pushHighlight = (
  highlights: DiffHighlight[],
  highlight: DiffHighlight,
) => {
  if (highlights.length >= 5) return;
  highlights.push(highlight);
};

const appendSentenceAlign = (
  leftSegments: DiffSegment[],
  rightSegments: DiffSegment[],
  highlights: DiffHighlight[],
  leftBlock: string,
  rightBlock: string,
) => {
  const rows = lcsAlign(splitSentences(leftBlock), splitSentences(rightBlock));
  for (const row of rows) {
    if (row.status === "equal" && row.left) {
      leftSegments.push({ text: row.left, status: "equal" });
      rightSegments.push({ text: row.right || row.left, status: "equal" });
      continue;
    }
    if (row.status === "changed" && row.left && row.right) {
      leftSegments.push({ text: row.left, status: "changed" });
      rightSegments.push({ text: row.right, status: "changed" });
      pushHighlight(highlights, {
        kind: "changed",
        left: row.left,
        right: row.right,
      });
      continue;
    }
    if (row.status === "removed" && row.left) {
      leftSegments.push({ text: row.left, status: "removed" });
      pushHighlight(highlights, { kind: "removed", left: row.left });
      continue;
    }
    if (row.status === "added" && row.right) {
      rightSegments.push({ text: row.right, status: "added" });
      pushHighlight(highlights, { kind: "added", right: row.right });
    }
  }
};

/** Build dual-side sentence highlights for knowledge-conflict comparison. */
export const buildKnowledgeConflictDiff = (
  leftBody: string,
  rightBody: string,
): KnowledgeConflictDiff => {
  const leftBlocks = splitBlocks(leftBody);
  const rightBlocks = splitBlocks(rightBody);

  if (!leftBlocks.length && !rightBlocks.length) {
    return {
      leftSegments: [],
      rightSegments: [],
      highlights: [],
      changeCount: 0,
    };
  }

  const leftSegments: DiffSegment[] = [];
  const rightSegments: DiffSegment[] = [];
  const highlights: DiffHighlight[] = [];

  for (const row of lcsAlign(leftBlocks, rightBlocks)) {
    if (row.status === "equal" && row.left) {
      for (const sentence of splitSentences(row.left)) {
        leftSegments.push({ text: sentence, status: "equal" });
        rightSegments.push({ text: sentence, status: "equal" });
      }
      continue;
    }
    if (row.status === "changed" && row.left && row.right) {
      appendSentenceAlign(
        leftSegments,
        rightSegments,
        highlights,
        row.left,
        row.right,
      );
      continue;
    }
    if (row.status === "removed" && row.left) {
      for (const sentence of splitSentences(row.left)) {
        leftSegments.push({ text: sentence, status: "removed" });
        pushHighlight(highlights, { kind: "removed", left: sentence });
      }
      continue;
    }
    if (row.status === "added" && row.right) {
      for (const sentence of splitSentences(row.right)) {
        rightSegments.push({ text: sentence, status: "added" });
        pushHighlight(highlights, { kind: "added", right: sentence });
      }
    }
  }

  const changeCount =
    leftSegments.filter((segment) => segment.status !== "equal").length +
    rightSegments.filter((segment) => segment.status !== "equal").length;

  return { leftSegments, rightSegments, highlights, changeCount };
};

export const truncateDiffText = (text: string, max = 48): string => {
  const normalized = normalizeKey(text);
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1)}…`;
};

export const formatDiffHighlightLabel = (
  highlight: DiffHighlight,
  labels: {
    added: string;
    removed: string;
    changed: string;
  },
): string => {
  if (highlight.kind === "added" && highlight.right) {
    return `${labels.added}${truncateDiffText(highlight.right)}`;
  }
  if (highlight.kind === "removed" && highlight.left) {
    return `${labels.removed}${truncateDiffText(highlight.left)}`;
  }
  if (highlight.kind === "changed" && highlight.left && highlight.right) {
    return labels.changed
      .replace("{left}", truncateDiffText(highlight.left, 28))
      .replace("{right}", truncateDiffText(highlight.right, 28));
  }
  return truncateDiffText(highlight.left || highlight.right || "");
};

export const buildConflictListSubtitle = (
  triggerSource: string,
  highlight: DiffHighlight | undefined,
  labels: {
    added: string;
    removed: string;
    changed: string;
  },
): string => {
  const point = highlight
    ? formatDiffHighlightLabel(highlight, labels)
    : "";
  if (triggerSource && point) return `${triggerSource} · ${point}`;
  return triggerSource || point;
};
