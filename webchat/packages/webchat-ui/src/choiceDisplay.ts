export interface WebchatChoiceOption {
  key: string;
  label: string;
  disabled?: boolean;
}

export interface WebchatChoiceValue {
  title?: string;
  description?: string;
  options?: WebchatChoiceOption[];
  answered?: boolean;
  selected?: string;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 从历史正文还原选择题。至少两项编号选项。 */
export function choiceValueFromVisibleText(content: string): WebchatChoiceValue | null {
  const lines = String(content || '').split(/\r?\n/);
  let start = -1;
  const labels: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].trim().match(/^\d+[.、]\s+(.+)$/);
    if (!match) {
      if (labels.length >= 2) break;
      start = -1;
      labels.length = 0;
      continue;
    }
    if (start < 0) start = index;
    labels.push(match[1].trim());
  }
  if (labels.length < 2 || start < 0) return null;
  let title = '';
  for (let index = start - 1; index >= 0; index -= 1) {
    const line = lines[index].trim();
    if (!line) continue;
    title = line;
    break;
  }
  if (!title || !/[?？]/.test(title) && !title.includes('请选择') && !title.includes('请确认')) return null;
  return {
    title,
    options: labels.map((label) => ({ key: label, label })),
  };
}

function choiceLabels(value: WebchatChoiceValue | undefined): string[] {
  return (value?.options || []).map((option) => (option.label || option.key || '').trim()).filter(Boolean);
}

/** 选择卡片已经展示时，去掉正文里重复的编号列表和只含选项名的表格。 */
export function stripWebchatChoiceDump(content: string, value: WebchatChoiceValue | undefined): string {
  const labels = choiceLabels(value);
  if (!content || labels.length === 0) {
    return content || '';
  }
  const labelSet = new Set(labels);
  const title = (value?.title || '').trim();
  const numbered = labels.map((label) => `\\d+[.、]\\s*${escapeRegExp(label)}`).join('\\s*\\n\\s*');
  const titlePart = title ? `${escapeRegExp(title)}\\s*\\n+\\s*` : '';
  let text = content.replace(new RegExp(`${titlePart}${numbered}`, 'g'), '');

  const lines = text.split('\n');
  const kept: string[] = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim().startsWith('|')) {
      kept.push(lines[index]);
      index += 1;
      continue;
    }
    const block: string[] = [];
    while (index < lines.length && lines[index].trim().startsWith('|')) {
      block.push(lines[index]);
      index += 1;
    }
    const cells = block.flatMap((line) => line.split('|').map((cell) => cell.trim()).filter(Boolean));
    const meaningful = cells.filter((cell) => !/^:?-+:?$/.test(cell));
    const onlyOptions = meaningful.length > 0 && meaningful.every((cell) => labelSet.has(cell));
    if (!onlyOptions) {
      kept.push(...block);
    }
  }
  text = kept.join('\n');
  if (title) {
    text = text.replace(new RegExp(`^\\s*${escapeRegExp(title)}\\s*$`, 'gm'), '');
  }
  return text.replace(/\n{3,}/g, '\n\n').trim();
}

export function attachChoiceHistory<T extends { sender: string; content: string | unknown; metadata?: Record<string, unknown> }>(
  messages: T[],
): T[] {
  return messages.map((message, index) => {
    if (message.sender !== 'bot' || typeof message.content !== 'string') return message;
    const choice = choiceValueFromVisibleText(message.content);
    if (!choice) return message;
    const later = messages.slice(index + 1).find((item) => item.sender === 'user' && typeof item.content === 'string' && item.content.trim());
    const answer = typeof later?.content === 'string' ? later.content.trim() : '';
    const matched = choice.options?.find((option) => option.label === answer || option.key === answer);
    return {
      ...message,
      content: stripWebchatChoiceDump(message.content, choice),
      metadata: {
        ...(message.metadata || {}),
        userChoice: {
          ...choice,
          answered: Boolean(later),
          selected: matched?.key,
        },
      },
    };
  });
}
