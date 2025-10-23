"use client";
import { signIn } from "next-auth/react";
import { useState, useEffect } from "react";
import Image from "next/image";
import { Select, Input } from "antd";
import PasswordResetForm from "./PasswordResetForm";
import OtpVerificationForm from "./OtpVerificationForm";
import { saveAuthToken } from "@/utils/crossDomainAuth";

interface SigninClientProps {
  searchParams: {
    callbackUrl: string;
    error: string;
  };
  signinErrors: Record<string | "default", string>;
}

type AuthStep = 'login' | 'reset-password' | 'otp-verification';

interface LoginResponse {
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  qrcode?: boolean;
  token?: string;
  username?: string;
  id?: string;
  locale?: string;
  redirect_url?: string;
}

interface WeChatSettings {
  enabled: boolean;
  app_id?: string;
  app_secret?: string;
  redirect_uri?: string;
}

interface BkSettings {
  is_open_logining: boolean;
  url?: string;
}

export default function SigninClient({ searchParams: { callbackUrl, error }, signinErrors }: SigninClientProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [domain, setDomain] = useState("");
  const [domainList, setDomainList] = useState<string[]>([]);
  const [loadingDomains, setLoadingDomains] = useState(true);
  const [formError, setFormError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isWechatBrowser, setIsWechatBrowser] = useState(false);
  const [authStep, setAuthStep] = useState<AuthStep>('login');
  const [loginData, setLoginData] = useState<LoginResponse>({});
  const [qrCodeUrl, setQrCodeUrl] = useState<string>("");
  const [wechatSettings, setWechatSettings] = useState<WeChatSettings | null>(null);
  const [loadingWechatSettings, setLoadingWechatSettings] = useState(true);
  const [bkSettings, setBkSettings] = useState<BkSettings | null>(null);
  const [loadingBkSettings, setLoadingBkSettings] = useState(true);

  useEffect(() => {
    const userAgent = navigator.userAgent.toLowerCase();
    setIsWechatBrowser(userAgent.includes('micromessenger') || userAgent.includes('wechat'));
    
    // Fetch WeChat settings, BK settings and domain list
    fetchWechatSettings();
    fetchBkSettings();
    fetchDomainList();
  }, []);

  const fetchDomainList = async () => {
    try {
      setLoadingDomains(true);
      const response = await fetch('/api/proxy/core/api/get_domain_list/', {
        method: "GET",
        headers: { 
          "Content-Type": "application/json" 
        },
      });
      
      const responseData = await response.json();
      
      if (response.ok && responseData.result && Array.isArray(responseData.data)) {
        setDomainList(responseData.data);
        // Set default domain if available
        if (responseData.data.length > 0) {
          setDomain(responseData.data[0]);
        }
      } else {
        console.error("Failed to fetch domain list:", responseData);
        setDomainList([]);
      }
    } catch (error) {
      console.error("Failed to fetch domain list:", error);
      setDomainList([]);
    } finally {
      setLoadingDomains(false);
    }
  };

  const fetchWechatSettings = async () => {
    try {
      setLoadingWechatSettings(true);
      const response = await fetch("/api/proxy/core/api/get_wechat_settings/", {
        method: "GET",
        headers: { 
          "Content-Type": "application/json" 
        },
      });
      
      const responseData = await response.json();
      
      if (response.ok && responseData.result) {
        setWechatSettings({
          enabled: true,
          ...responseData.data
        });
      } else {
        setWechatSettings({ enabled: false });
      }
    } catch (error) {
      console.error("Failed to fetch WeChat settings:", error);
      setWechatSettings({ enabled: false });
    } finally {
      setLoadingWechatSettings(false);
    }
  };

  const fetchBkSettings = async () => {
    try {
      setLoadingBkSettings(true);
      const response = await fetch('/api/proxy/core/api/get_bk_settings/', {
        method: "GET",
        headers: { 
          "Content-Type": "application/json" 
        },
      });

      const responseData = await response.json();

      if (response.ok && responseData.result) {
        setBkSettings({
          is_open_logining: responseData.data.bk_login_open,
          url: responseData.data.url,
        });
      } else {
        setBkSettings({ is_open_logining: false });
      }
    } catch (error) {
      console.error("Failed to fetch BK settings:", error);
      setBkSettings({ is_open_logining: false });
    } finally {
      setLoadingBkSettings(false);
    }
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setFormError("");
    
    try {
      const response = await fetch('/api/proxy/core/api/login/', {
        method: "POST",
        headers: { 
          "Content-Type": "application/json" 
        },
        body: JSON.stringify({
          username,
          password,
          domain,
        }),
      });
      
      const responseData = await response.json();
      
      if (!response.ok || !responseData.result) {
        setFormError(responseData.message || "Login failed");
        setIsLoading(false);
        return;
      }
      
      const userData = responseData.data;
      setLoginData(userData);
      
      if (userData.temporary_pwd) {
        setAuthStep('reset-password');
        setIsLoading(false);
        return;
      }
      
      if (userData.enable_otp) {
        if (userData.qrcode) {
          try {
            const qrResponse = await fetch(`/api/proxy/core/api/generate_qr_code/?username=${encodeURIComponent(userData.username)}`, {
              method: "GET",
              headers: { 
                "Content-Type": "application/json" 
              },
            });
            const qrData = await qrResponse.json();
            if (qrResponse.ok && qrData.result) {
              setQrCodeUrl(qrData.data.qr_code);
            }
          } catch (error) {
            console.error("Failed to generate QR code:", error);
          }
        }
        setAuthStep('otp-verification');
        setIsLoading(false);
        return;
      }
      
      // Complete authentication first, then handle redirect_url
      await completeAuthentication(userData);
      
    } catch (error) {
      console.error("Login error:", error);
      setFormError("An error occurred during login");
      setIsLoading(false);
    }
  };

  const handlePasswordResetComplete = async (updatedLoginData: LoginResponse) => {
    setLoginData(updatedLoginData);
    
    if (updatedLoginData.enable_otp) {
      if (updatedLoginData.qrcode) {
        try {
          const qrResponse = await fetch(`/api/proxy/core/api/generate_qr_code/?username=${encodeURIComponent(updatedLoginData.username || '')}`, {
            method: "GET",
            headers: { 
              "Content-Type": "application/json" 
            },
          });
          const qrData = await qrResponse.json();
          if (qrResponse.ok && qrData.result) {
            setQrCodeUrl(qrData.data.qr_code || qrData.data.qr_code_url);
          }
        } catch (error) {
          console.error("Failed to generate QR code:", error);
        }
      }
      setAuthStep('otp-verification');
      return;
    }
    
    await completeAuthentication(updatedLoginData);
  };

  const handleOtpVerificationComplete = async (loginData: LoginResponse) => {
    await completeAuthentication(loginData);
  };

  const completeAuthentication = async (userData: LoginResponse) => {
    try {
      const userDataForAuth = {
        id: userData.id || userData.username || 'unknown',
        username: userData.username,
        token: userData.token,
        locale: userData.locale || 'en',
        temporary_pwd: userData.temporary_pwd || false,
        enable_otp: userData.enable_otp || false,
        qrcode: userData.qrcode || false,
      };

      console.log('Completing authentication with user data:', userDataForAuth);

      if (userData.token) {
        saveAuthToken({
          id: userDataForAuth.id,
          username: userDataForAuth.username || '',
          token: userData.token,
          locale: userDataForAuth.locale,
          temporary_pwd: userDataForAuth.temporary_pwd,
          enable_otp: userDataForAuth.enable_otp,
          qrcode: userDataForAuth.qrcode,
        });
      }

      const result = await signIn("credentials", {
        redirect: false,
        username: userDataForAuth.username,
        password: password,
        skipValidation: 'true',
        userData: JSON.stringify(userDataForAuth),
        callbackUrl: callbackUrl || "/",
      }) as any;
      
      console.log('SignIn result:', result);
      
      if (result?.error) {
        console.error('SignIn error:', result.error);
        setFormError(result.error);
        setIsLoading(false);
      } else if (result?.ok) {
        if (userData.redirect_url) {
          console.log('Redirecting to server-provided redirect_url:', userData.redirect_url);
          window.location.href = userData.redirect_url;
        } else {
          console.log('SignIn successful, redirecting to:', callbackUrl || "/");
          window.location.href = callbackUrl || "/";
        }
      } else {
        console.error('SignIn failed with unknown error');
        setFormError("Authentication failed");
        setIsLoading(false);
      }
    } catch (error) {
      console.error("Failed to complete authentication:", error);
      setFormError("Authentication failed");
      setIsLoading(false);
    }
  };

  const handleWechatSignIn = async () => {
    console.log("Starting WeChat login process...");
    console.log("Callback URL:", callbackUrl || "/");
    
    signIn("wechat", { 
      callbackUrl: callbackUrl || "/",
      redirect: true
    });
  };

  const handleBkSignIn = () => {
    if (bkSettings?.url) {
      const currentDomain = window.location.origin;
      const bkLoginUrl = `${bkSettings.url}?callbackUrl=${encodeURIComponent(currentDomain)}`;
      console.log("Redirecting to BK login:", bkLoginUrl);
      window.location.href = bkLoginUrl;
    }
  };

  const renderLoginForm = () => (
    <form onSubmit={handleLoginSubmit} className="flex flex-col space-y-6 w-full">
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <label htmlFor="domain" className="text-sm font-medium text-[var(--color-text-1)]">Domain</label>
          {loadingDomains && (
            <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin"></div>
          )}
        </div>
        <Select
          id="domain"
          value={domain || undefined}
          onChange={setDomain}
          placeholder={loadingDomains ? 'Loading domains...' : 'Select a domain'}
          loading={loadingDomains}
          disabled={loadingDomains}
          className="w-full"
          size="middle"
          style={{ height: '48px' }}
          dropdownStyle={{ 
            borderRadius: '8px',
            boxShadow: '0 10px 25px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)'
          }}
          options={domainList.map(domainItem => ({
            label: domainItem,
            value: domainItem,
          }))}
          notFoundContent={
            loadingDomains ? (
              <div className="flex items-center justify-center py-4">
                <div className="w-4 h-4 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin mr-2"></div>
                Loading...
              </div>
            ) : (
              <div className="flex items-center justify-center py-4 text-gray-500">
                <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                No domains available
              </div>
            )
          }
        />
        {/* Error state indicator */}
        {!loadingDomains && domainList.length === 0 && (
          <p className="text-sm text-amber-600 flex items-center mt-1">
            <svg className="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            No domains available
          </p>
        )}
      </div>

      <div className="space-y-2">
        <label htmlFor="username" className="text-sm font-medium text-[var(--color-text-1)]">Username</label>
        <Input
          id="username"
          placeholder="Enter your username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          size="large"
          required
          className="h-12"
        />
      </div>
      
      <div className="space-y-2">
        <label htmlFor="password" className="text-sm font-medium text-[var(--color-text-1)]">Password</label>
        <Input.Password
          id="password"
          placeholder="Enter your password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          size="large"
          required
          className="h-12"
        />
      </div>
      
      <button 
        type="submit" 
        disabled={isLoading}
        className={`w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg shadow transition-all duration-150 ease-in-out transform hover:-translate-y-0.5 ${isLoading ? 'opacity-70 cursor-not-allowed' : ''}`}
      >
        {isLoading ? (
          <span className="flex items-center justify-center">
            <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 718-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 714 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Signing in...
          </span>
        ) : 'Sign In'}
      </button>
    </form>
  );

  const renderPasswordResetForm = () => (
    <PasswordResetForm
      username={username}
      loginData={loginData}
      onPasswordReset={handlePasswordResetComplete}
      onError={setFormError}
    />
  );

  const renderOtpVerificationForm = () => (
    <OtpVerificationForm
      username={username}
      loginData={loginData}
      qrCodeUrl={qrCodeUrl}
      onOtpVerification={handleOtpVerificationComplete}
      onError={setFormError}
    />
  );

  const renderWechatLoginSection = () => {
    const isLoading = loadingWechatSettings || loadingBkSettings;
    const hasWechat = wechatSettings?.enabled;
    const hasBkLogin = bkSettings?.is_open_logining;
    const hasAnyLogin = hasWechat || hasBkLogin;

    if (isLoading) {
      return (
        <div className="mt-6">
          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-[var(--color-border-3)]"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-[var(--color-bg)] text-[var(--color-text-1)]">Or continue with</span>
            </div>
          </div>
          
          <div className="mt-6 space-y-3">
            <div className="w-full h-12 bg-gray-200 rounded-lg animate-pulse"></div>
            {loadingBkSettings && (
              <div className="w-full h-12 bg-gray-200 rounded-lg animate-pulse"></div>
            )}
          </div>
        </div>
      );
    }

    if (!hasAnyLogin) {
      return null;
    }

    return (
      <div className="mt-6">
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-[var(--color-border-3)]"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-[var(--color-bg)] text-[var(--color-text-1)]">Or continue with</span>
          </div>
        </div>
        
        <div className="mt-6 space-y-3">
          {hasWechat && (
            <button
              onClick={handleWechatSignIn}
              className="w-full flex items-center justify-center px-4 py-3 text-sm font-medium rounded-lg shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 transition-colors duration-200"
            >
              Sign in with WeChat
            </button>
          )}
          
          {hasBkLogin && (
            <button
              onClick={handleBkSignIn}
              className="w-full flex items-center justify-center px-4 py-3 text-sm font-medium rounded-lg shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-colors duration-200"
            >
              Sign in with BlueKing
            </button>
          )}
        </div>
        
        {isWechatBrowser && hasWechat && (
          <div className="mt-4 text-center text-sm text-green-600">
            You are using WeChat browser, for best experience use the WeChat login.
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex w-[calc(100%+2rem)] h-screen -m-4">
      <div 
        className="w-3/5 hidden md:block bg-gradient-to-br from-blue-500 to-indigo-700"
        style={{
          backgroundImage: "url('/system-login-bg.jpg')",
          backgroundSize: "cover",
          backgroundPosition: "center"
        }}
      >
      </div>
      
      <div className="w-full h-full md:w-2/5 flex items-center justify-center p-8 bg-[var(--bg-color-1)] overflow-y-auto">
        <div className="w-full h-full max-w-md">
          <div className="text-center mb-10">
            <div className="flex justify-center mb-6">
              <Image src="/logo-site.png" alt="Logo" width={60} height={60} className="h-14 w-auto" />
            </div>
            <h2 className="text-3xl font-bold text-[var(--color-text-1)]">
              {authStep === 'login' && 'Sign In'}
              {authStep === 'reset-password' && 'Reset Password'}
              {authStep === 'otp-verification' && 'Verify Identity'}
            </h2>
            <p className="text-[var(--color-text-3)] mt-2">
              {authStep === 'login' && 'Enter your credentials to continue'}
              {authStep === 'reset-password' && 'Create a new password to secure your account'}
              {authStep === 'otp-verification' && 'Complete the verification process'}
            </p>
          </div>
          
          {error && (
            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 p-4 rounded mb-6">
              <p className="font-medium">{signinErrors[error.toLowerCase()]}</p>
            </div>
          )}
          
          {formError && (
            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 p-4 rounded mb-6">
              <p className="font-medium">{formError}</p>
            </div>
          )}
          
          {authStep === 'login' && renderLoginForm()}
          {authStep === 'reset-password' && renderPasswordResetForm()}
          {authStep === 'otp-verification' && renderOtpVerificationForm()}
          
          {authStep === 'login' && renderWechatLoginSection()}
        </div>
      </div>
    </div>
  );
}