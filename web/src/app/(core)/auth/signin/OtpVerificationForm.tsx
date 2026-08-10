"use client";
import {useState} from "react";
import {Button, Input} from "antd";
import {useTranslation} from "@/utils/i18n";

interface LoginResponse {
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  qrcode?: boolean;
  token?: string;
  username?: string;
  id?: string;
  locale?: string;
  timezone?: string;
  password_expiry_reminder?: string;
  // OTP two-phase authentication fields
  require_otp?: boolean;
  challenge_id?: string;
  qr_code?: string;  // QR code for first-time OTP binding
  need_binding?: boolean;  // Flag indicating first-time OTP binding
}

interface OtpVerificationFormProps {
  username: string;
  loginData: LoginResponse;
  qrCodeUrl: string;
  onOtpVerification: (loginData: LoginResponse) => void;
  onError: (error: string) => void;
}

export default function OtpVerificationForm({ 
  username, 
  loginData, 
  qrCodeUrl, 
  onOtpVerification, 
  onError 
}: OtpVerificationFormProps) {
  const [otpCode, setOtpCode] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { t } = useTranslation();

  const handleOtpVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!otpCode) {
      onError(t('signin.errors.otpRequired'));
      return;
    }

    if (!loginData.challenge_id) {
      onError(t('signin.errors.invalidSession'));
      return;
    }
    
    setIsLoading(true);
    onError("");
    
    try {
      // Two-phase authentication: verify OTP with challenge_id to get token
      const response = await fetch('/api/proxy/core/api/verify_otp_login/', {
        method: "POST",
        headers: { 
          "Content-Type": "application/json" 
        },
        body: JSON.stringify({
          challenge_id: loginData.challenge_id,
          otp_code: otpCode
        }),
      });
      
      const responseData = await response.json();
      
      if (response.ok && responseData.result) {
        // OTP verification successful, token is now in responseData.data
        const verifiedLoginData: LoginResponse = {
          ...loginData,
          token: responseData.data.token,
          id: responseData.data.id || loginData.id,
          locale: responseData.data.locale || loginData.locale,
          timezone: responseData.data.timezone || loginData.timezone,
          temporary_pwd: responseData.data.temporary_pwd ?? loginData.temporary_pwd,
          password_expiry_reminder: responseData.data.password_expiry_reminder,
          // Clear challenge_id as it's been used
          challenge_id: undefined,
          require_otp: false,
        };
        onOtpVerification(verifiedLoginData);
      } else {
        onError(responseData.message || t('signin.errors.invalidOtp'));
        setIsLoading(false);
      }
    } catch (error) {
      console.error("Error verifying OTP:", error);
      onError(t('signin.errors.otpVerifyFailed'));
      setIsLoading(false);
    }
  };

  return (
    <div>
      <div className="text-center mb-6">
        <h3 className="text-xl font-semibold text-[var(--color-text-1)]">{t('signin.otp.title')}</h3>
        <p className="text-[var(--color-text-2)] mt-2">{t('signin.otp.description')}</p>
      </div>
      
      {qrCodeUrl && (
        <div className="mb-6">
          <p className="text-sm text-[var(--color-text-1)] mb-3">{t('signin.otp.installAppsStep')}</p>
          <div className="text-sm text-[var(--color-text-2)] mb-3 pl-4">
            <div>Microsoft Authenticator</div>
            <div>FreeOTP</div>
            <div>Google Authenticator</div>
          </div>
          <p className="text-sm text-[var(--color-text-1)] mb-3">{t('signin.otp.scanQrStep')}</p>
          <div className="flex pl-4">
            <img src={`data:image/png;base64, ${qrCodeUrl}`} alt={t('signin.otp.qrAlt')} className="h-48 w-48 rounded-md border border-(--color-border)" />
          </div>
        </div>
      )}
      
      <form onSubmit={handleOtpVerification} className="flex flex-col space-y-6 w-full">
        <div className="space-y-2">
          <label htmlFor="username-display-otp" className="text-sm font-medium text-[var(--color-text-1)]">{t('signin.form.username')}</label>
          <Input
            id="username-display-otp"
            type="text"
            value={loginData.username || username}
            className="w-full"
            size="large"
            disabled
          />
        </div>
        
        <div className="space-y-2">
          <label htmlFor="otp-code" className="text-sm font-medium text-[var(--color-text-1)]">{t('signin.otp.verificationCode')}</label>
          <Input
            id="otp-code"
            type="text"
            placeholder={t('signin.otp.codePlaceholder')}
            value={otpCode}
            onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            className="w-full text-center text-lg tracking-wider"
            maxLength={6}
            required
          />
        </div>
        
        <Button 
          type="primary"
          htmlType="submit" 
          loading={isLoading}
          className="w-full"
          size="large"
        >
          {isLoading ? t('signin.otp.verifying') : t('signin.otp.verifyCode')}
        </Button>
      </form>
    </div>
  );
}
