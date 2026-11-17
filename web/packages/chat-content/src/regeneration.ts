/** Regeneration appends a new turn using the selected turn's complete input. */
export function findRegenerationMessage<
  T extends { id: string; role?: string; sender?: string },
>(messages: readonly T[], id: string): T | null {
  const target = messages.findIndex((message) => message.id === id);
  for (let index = target; index >= 0; index--) {
    if ((messages[index].role ?? messages[index].sender) === "user")
      return messages[index];
  }
  return null;
}
