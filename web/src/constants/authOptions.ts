import CredentialsProvider from "next-auth/providers/credentials";
import type { NextAuthOptions } from "next-auth";
import type {JWT} from "next-auth/jwt";
import {normalizeLocale, normalizeTimezone} from "@/utils/userPreferences";
import WeChatProvider from "../lib/wechatProvider";

type ExtendedJWT = JWT & { timezone?: string };

const buildAuthUser = (userData: any) => ({
  id: userData.id || userData.username,
  username: userData.username,
  token: userData.token,
  locale: normalizeLocale(userData.locale || 'en'),
  timezone: normalizeTimezone(userData.timezone || 'Asia/Shanghai'),
  temporary_pwd: userData.temporary_pwd || false,
  enable_otp: userData.enable_otp || false,
  qrcode: userData.qrcode || false,
  provider: userData.provider,
  wechatOpenId: userData.wechatOpenId,
  wechatUnionId: userData.wechatUnionId,
  wechatWorkId: userData.wechatWorkId,
});

const applyUserToToken = (token: ExtendedJWT, user: any, account?: any) => {
  token.id = user.id;
  token.username = user.username || user.name || '';
  token.locale = normalizeLocale(user.locale || token.locale || 'en');
  token.timezone = normalizeTimezone(user.timezone || token.timezone || 'Asia/Shanghai');
  token.zoneinfo = token.timezone;
  token.token = user.token;
  token.temporary_pwd = user.temporary_pwd;
  token.enable_otp = user.enable_otp;
  token.qrcode = user.qrcode;
  token.provider = account?.provider || user.provider;
  token.wechatOpenId = user.wechatOpenId;
  token.wechatUnionId = user.wechatUnionId;
  token.wechatWorkId = user.wechatWorkId;
  return token;
};

const applySessionUpdateToToken = (token: ExtendedJWT, session: any) => {
  const sessionUser = session?.user || {};
  token.locale = normalizeLocale(sessionUser.locale || session?.locale || token.locale || 'en');
  token.timezone = normalizeTimezone(sessionUser.timezone || session?.timezone || token.timezone || 'Asia/Shanghai');
  token.zoneinfo = token.timezone;
  return token;
};

const buildSessionFromToken = (session: any, token: ExtendedJWT) => {
  session.user = {
    id: token.id || '',
    username: token.username,
    locale: token.locale,
    timezone: token.timezone,
    token: token.token,
    temporary_pwd: token.temporary_pwd,
    enable_otp: token.enable_otp,
    qrcode: token.qrcode,
    provider: token.provider,
    wechatOpenId: token.wechatOpenId,
    wechatUnionId: token.wechatUnionId,
    wechatWorkId: token.wechatWorkId,
  };
  session.locale = token.locale;
  session.timezone = token.timezone;
  session.zoneinfo = token.timezone;
  return session;
};

async function getWeChatConfig() {
  try {
    const response = await fetch(`${process.env.NEXTAPI_URL}/api/v1/core/api/get_wechat_settings/`, {
      method: "GET",
      headers: { 
        "Content-Type": "application/json",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
      },
      cache: "no-store"
    });
    
    const responseData = await response.json();
    
    if (!response.ok || !responseData.result) {
      console.error("Failed to get WeChat settings:", responseData);
      return null;
    }
    return responseData.data;
  } catch (error) {
    console.error("Error fetching WeChat settings:", error);
    return null;
  }
}

export async function getAuthOptions(): Promise<NextAuthOptions> {
  const wechatConfig = await getWeChatConfig();
  
  const providers = [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
        domain: { label: "Domain", type: "text" },
        skipValidation: { label: "Skip Validation", type: "text" },
        userData: { label: "User Data", type: "text" },
      },
      async authorize(credentials) {
        if (!credentials) {
          console.error("No credentials provided");
          return null;
        }

        try {
          // If skipValidation is true, use the provided userData directly
          // This is used when the login validation has already been done in SigninClient
          if (credentials.skipValidation === 'true' && credentials.userData) {
            const userData = JSON.parse(credentials.userData);

            // Ensure required fields are present
            if (!userData.id && !userData.username) {
              console.error("Invalid userData: missing id and username");
              return null;
            }

            return buildAuthUser(userData);
          }

          // Otherwise, perform normal login validation (for direct NextAuth usage)
          const response = await fetch(`${process.env.NEXTAPI_URL}/api/v1/core/api/login/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              username: credentials.username,
              password: credentials.password,
              domain: credentials.domain,
            }),
          });
          
          const responseData = await response.json();
          
          if (!response.ok || !responseData.result) {
            console.error("Authentication failed:", responseData);
            return null;
          }
          
          if (responseData.result) {
            const user = responseData.data;
            return buildAuthUser(user);
          }
        } catch (error) {
          console.error("Error during authentication:", error);
          return null;
        }
        
        return null;
      },
    }),
  ];
  
  if (wechatConfig && wechatConfig.app_id) {
    providers.push(
      WeChatProvider({
        clientId: wechatConfig.app_id,
        clientSecret: "", // 不再需要，OAuth 验证已移至后端
        redirectUri: `${wechatConfig.redirect_uri}/api/auth/callback/wechat`,
      }) as unknown as any
    );
  }

  return {
    providers,
    pages: {
      signIn: '/auth/signin',
      signOut: '/auth/signout',
    },
    session: {
      strategy: "jwt",
      maxAge: 60 * 60 * 24,
    },
    callbacks: {
      async jwt({ token, user, account, trigger, session }) {
        const extToken = token as ExtendedJWT;
        if (user) {
          return applyUserToToken(extToken, user, account);
        }

        if (trigger === 'update' && session) {
          return applySessionUpdateToToken(extToken, session);
        }

        return extToken;
      },
      async session({ session, token }) {
        return buildSessionFromToken(session, token as ExtendedJWT);
      },
    },
  };
}

// For backward compatibility, keep a default authOptions, but only include basic CredentialsProvider
export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        username: { label: "Username", type: "text" },
        password: { label: "Password", type: "password" },
        domain: { label: "Domain", type: "text" },
        skipValidation: { label: "Skip Validation", type: "text" },
        userData: { label: "User Data", type: "text" },
      },
      async authorize(credentials) {
        if (!credentials) {
          console.error("No credentials provided");
          return null;
        }

        try {
          // If skipValidation is true, use the provided userData directly
          if (credentials.skipValidation === 'true' && credentials.userData) {
            const userData = JSON.parse(credentials.userData);
            
            if (!userData.id && !userData.username) {
              console.error("Invalid userData: missing id and username");
              return null;
            }

            return buildAuthUser(userData);
          }

          // Otherwise, perform normal login validation
          const response = await fetch(`${process.env.NEXTAPI_URL}/api/v1/core/api/login/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              username: credentials.username,
              password: credentials.password,
              domain: credentials.domain,
            }),
          });
          
          const responseData = await response.json();
          
          if (!response.ok || !responseData.result) {
            console.error("Authentication failed:", responseData);
            return null;
          }
          
          if (responseData.result) {
            const user = responseData.data;
            return buildAuthUser(user);
          }
        } catch (error) {
          console.error("Error during authentication:", error);
          return null;
        }
        
        return null;
      },
    }),
  ],
  pages: {
    signIn: '/auth/signin',
    signOut: '/auth/signout',
  },
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 24,
  },
  callbacks: {
    async jwt({ token, user, account, trigger, session }) {
      const extToken = token as ExtendedJWT;
      if (user) {
        return applyUserToToken(extToken, user, account);
      }

      if (trigger === 'update' && session) {
        return applySessionUpdateToToken(extToken, session);
      }

      return extToken;
    },
    async session({ session, token }) {
      return buildSessionFromToken(session, token as ExtendedJWT);
    },
  },
};