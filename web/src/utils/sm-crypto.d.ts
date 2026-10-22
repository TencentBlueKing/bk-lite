declare module "sm-crypto" {
  export function sm3(
    input: string | ArrayLike<number>,
    options?: { key: string | ArrayLike<number>; mode?: "hmac" },
  ): string;

  export const sm2: {
    doEncrypt(msg: string | ArrayLike<number>, publicKey: string, cipherMode?: number): string;
    doDecrypt(
      encryptData: string,
      privateKey: string,
      cipherMode?: number,
      options?: { output?: "string" | "array" },
    ): string | number[];
  };

  export const sm4: {
    encrypt(
      input: string | ArrayLike<number>,
      key: string | ArrayLike<number>,
      options?: {
        mode?: string;
        iv?: string | number[];
        padding?: string;
        output?: "string" | "array";
      },
    ): string | number[];
    decrypt(
      input: string | ArrayLike<number>,
      key: string | ArrayLike<number>,
      options?: {
        mode?: string;
        iv?: string | number[];
        padding?: string;
        output?: "string" | "array";
      },
    ): string | number[];
  };
}
