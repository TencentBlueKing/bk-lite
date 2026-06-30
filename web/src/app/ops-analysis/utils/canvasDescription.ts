export const resolveCanvasDescription = (itemDescription?: string | null) => {
  if (itemDescription?.trim()) {
    return itemDescription;
  }

  return undefined;
};
