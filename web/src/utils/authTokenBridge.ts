type ReplaceAuthToken = (token: string) => void;

let replaceAuthTokenHandler: ReplaceAuthToken | null = null;

export const registerAuthTokenReplacer = (handler: ReplaceAuthToken | null) => {
  replaceAuthTokenHandler = handler;
};

export const replaceAuthToken = (token: string) => {
  replaceAuthTokenHandler?.(token);
};
