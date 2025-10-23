import CredentialsProvider from "next-auth/providers/credentials";
import { AuthOptions } from "next-auth";
import WeChatProvider from "../lib/wechatProvider";

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
    console.log("WeChat settings fetched successfully:", responseData.data);
    return responseData.data;
  } catch (error) {
    console.error("Error fetching WeChat settings:", error);
    return null;
  }
}

export async function getAuthOptions(): Promise<AuthOptions> {
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
            console.log("Parsed userData:", userData);
            
            // Ensure required fields are present
            if (!userData.id && !userData.username) {
              console.error("Invalid userData: missing id and username");
              return null;
            }
            
            return {
              id: userData.id || userData.username,
              username: userData.username,
              token: userData.token,
              locale: userData.locale || 'en',
              temporary_pwd: userData.temporary_pwd || false,
              enable_otp: userData.enable_otp || false,
              qrcode: userData.qrcode || false,
              provider: userData.provider,
              wechatOpenId: userData.wechatOpenId,
              wechatUnionId: userData.wechatUnionId,
              wechatWorkId: userData.wechatWorkId,
            };
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
            return {
              id: user.id || user.username,
              username: user.username,
              token: user.token,
              locale: user.locale || 'en',
              temporary_pwd: user.temporary_pwd || false,
              enable_otp: user.enable_otp || false,
              qrcode: user.qrcode || false,
            };
          }
        } catch (error) {
          console.error("Error during authentication:", error);
          return null;
        }
        
        return null;
      },
    }),
  ];
  
  console.log("Credentials wechatConfig", wechatConfig);
  if (wechatConfig && wechatConfig.app_id && wechatConfig.app_secret) {
    providers.push(
      WeChatProvider({
        clientId: wechatConfig.app_id,
        clientSecret: wechatConfig.app_secret,
        redirectUri: `${wechatConfig.redirect_uri}/api/auth/callback/wechat`,
      }) as unknown as any
    );
    console.log("WeChat provider added successfully");
  } else {
    console.log("WeChat configuration is incomplete or unavailable. Skipping WeChat provider.");
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
      async jwt({ token, user, account }) {
        if (user) {
          token.id = user.id;
          token.username = user.username || user.name || '';
          token.locale = user.locale || 'en';
          token.token = user.token;
          token.temporary_pwd = user.temporary_pwd;
          token.enable_otp = user.enable_otp;
          token.qrcode = user.qrcode;
          token.provider = account?.provider;
          token.wechatOpenId = user.wechatOpenId;
          token.wechatUnionId = user.wechatUnionId;
          token.wechatWorkId = user.wechatWorkId;
        }
        return token;
      },
      async session({ session, token }) {
        session.user = {
          id: token.id || '',
          username: token.username,
          locale: token.locale,
          token: token.token,
          temporary_pwd: token.temporary_pwd,
          enable_otp: token.enable_otp,
          qrcode: token.qrcode,
          provider: token.provider,
          wechatOpenId: token.wechatOpenId,
          wechatUnionId: token.wechatUnionId,
          wechatWorkId: token.wechatWorkId,
        };
        return session;
      },
    },
  };
}

// For backward compatibility, keep a default authOptions, but only include basic CredentialsProvider
export const authOptions: AuthOptions = {
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
            
            return {
              id: userData.id || userData.username,
              username: userData.username,
              token: userData.token,
              locale: userData.locale || 'en',
              temporary_pwd: userData.temporary_pwd || false,
              enable_otp: userData.enable_otp || false,
              qrcode: userData.qrcode || false,
              provider: userData.provider,
              wechatOpenId: userData.wechatOpenId,
              wechatUnionId: userData.wechatUnionId,
              wechatWorkId: userData.wechatWorkId,
            };
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
            return {
              id: user.id || user.username,
              username: user.username,
              token: user.token,
              locale: user.locale || 'en',
              temporary_pwd: user.temporary_pwd || false,
              enable_otp: user.enable_otp || false,
              qrcode: user.qrcode || false,
            };
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
    async jwt({ token, user, account }) {
      if (user) {
        token.id = user.id;
        token.username = user.username || user.name || '';
        token.locale = user.locale || 'en';
        token.token = user.token;
        token.temporary_pwd = user.temporary_pwd;
        token.enable_otp = user.enable_otp;
        token.qrcode = user.qrcode;
        token.provider = account?.provider;
        token.wechatOpenId = user.wechatOpenId;
        token.wechatUnionId = user.wechatUnionId;
        token.wechatWorkId = user.wechatWorkId;
      }
      return token;
    },
    async session({ session, token }) {
      session.user = {
        id: token.id || '',
        username: token.username,
        locale: token.locale,
        token: token.token,
        temporary_pwd: token.temporary_pwd,
        enable_otp: token.enable_otp,
        qrcode: token.qrcode,
        provider: token.provider,
        wechatOpenId: token.wechatOpenId,
        wechatUnionId: token.wechatUnionId,
        wechatWorkId: token.wechatWorkId,
      };
      return session;
    },
  },
};