// Global type augmentations for the project
import 'next-auth';
import 'next-auth/jwt';

declare module 'next-auth' {
  interface Session {
    accessToken?: string;
    error?: string;
    locale?: string;
    username?: string;
    roles?: string[];
    zoneinfo?: string;
    temporary_pwd?: boolean;
    enable_otp?: boolean;
    qrcode?: boolean;
    user: {
      id: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
      username?: string;
      locale?: string;
      token?: string;
      temporary_pwd?: boolean;
      enable_otp?: boolean;
      qrcode?: boolean;
      wechatWorkId?: string;
      provider?: string;
      wechatOpenId?: string;
      wechatUnionId?: string;
    };
  }

  interface User {
    id: string;
    name?: string | null;
    email?: string | null;
    image?: string | null;
    username?: string;
    locale?: string;
    token?: string;
    temporary_pwd?: boolean;
    enable_otp?: boolean;
    qrcode?: boolean;
    wechatWorkId?: string;
    provider?: string;
    wechatOpenId?: string;
    wechatUnionId?: string;
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    idToken?: string;
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: number;
    locale?: string;
    error?: string;
    username?: string;
    roles?: string[];
    zoneinfo?: string;
    id?: string;
    token?: string;
    temporary_pwd?: boolean;
    enable_otp?: boolean;
    qrcode?: boolean;
    wechatWorkId?: string;
    provider?: string;
    wechatOpenId?: string;
    wechatUnionId?: string;
  }
}
