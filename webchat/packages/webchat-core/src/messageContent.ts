import type { MessageContent } from './types';

/** Extract the user-visible plain text from either legacy or multimodal content. */
export function extractMessageText(content: string | MessageContent[]): string {
  if (typeof content === 'string') {
    return content;
  }
  return content
    .flatMap((item) => {
      if (item.type === 'text' && item.text) {
        return [item.text];
      }
      if (item.type === 'message' && item.message) {
        return [item.message];
      }
      return [];
    })
    .join('\n');
}
