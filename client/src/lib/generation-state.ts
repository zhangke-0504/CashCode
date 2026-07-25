export type GenerationByChat = Record<string, boolean>;

export function isChatGenerating(state: GenerationByChat, chatId: string | null): boolean {
  return chatId ? state[chatId] === true : false;
}

export function setChatGenerating(
  state: GenerationByChat,
  chatId: string,
  generating: boolean,
): GenerationByChat {
  if (generating) {
    return state[chatId] ? state : { ...state, [chatId]: true };
  }
  if (!state[chatId]) return state;
  const next = { ...state };
  delete next[chatId];
  return next;
}
