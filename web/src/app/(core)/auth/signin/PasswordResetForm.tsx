"use client";
import { useState } from "react";
import { Input, Button } from "antd";
import { useTranslation } from "@/utils/i18n";

interface LoginResponse {
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  qrcode?: boolean;
  token?: string;
  username?: string;
  id?: string;
  locale?: string;
  timezone?: string;
}

interface PasswordResetFormProps {
  username: string;
  loginData: LoginResponse;
  onPasswordReset: (updatedLoginData: LoginResponse) => void;
  onError: (error: string) => void;
}

export default function PasswordResetForm({ 
  username, 
  loginData, 
  onPasswordReset, 
  onError 
}: PasswordResetFormProps) {
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const { t } = useTranslation();

  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (newPassword !== confirmPassword) {
      onError(t('signin.errors.passwordMismatch'));
      return;
    }
    
    if (newPassword.length < 8) {
      onError(t('signin.errors.passwordTooShort'));
      return;
    }
    
    setIsLoading(true);
    onError("");
    
    try {
      const response = await fetch('/api/proxy/core/api/reset_pwd/', {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${loginData.token}`,
        },
        body: JSON.stringify({
          password: newPassword
        }),
      });
      
      const responseData = await response.json();
      
      if (!response.ok || !responseData.result) {
        onError(responseData.message || t('signin.errors.passwordResetFailed'));
        setIsLoading(false);
        return;
      }
      
      // Update login data to remove temporary_pwd flag
      const updatedLoginData = { ...loginData, temporary_pwd: false };
      onPasswordReset(updatedLoginData);
      
    } catch (error) {
      console.error("Error resetting password:", error);
      onError(error instanceof Error ? error.message : t('signin.errors.unknown'));
      setIsLoading(false);
    }
  };

  return (
    <div>
      <div className="text-center mb-6">
        <h3 className="text-xl font-semibold text-[var(--color-text-1)]">{t('signin.passwordReset.title')}</h3>
        <p className="text-gray-500 mt-2">{t('signin.passwordReset.description')}</p>
      </div>
      
      <form onSubmit={handlePasswordReset} className="flex flex-col space-y-6 w-full">
        <div className="space-y-2">
          <label htmlFor="username-display" className="text-sm font-medium text-[var(--color-text-1)]">{t('signin.form.username')}</label>
          <Input
            id="username-display"
            type="text"
            value={loginData.username || username}
            className="w-full"
            size="large"
            disabled
          />
        </div>
        
        <div className="space-y-2">
          <label htmlFor="new-password" className="text-sm font-medium text-[var(--color-text-1)]">{t('signin.passwordReset.newPassword')}</label>
          <Input.Password
            id="new-password"
            placeholder={t('signin.passwordReset.newPasswordPlaceholder')}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full"
            size="large"
            required
          />
        </div>
        
        <div className="space-y-2">
          <label htmlFor="confirm-password" className="text-sm font-medium text-[var(--color-text-1)]">{t('signin.passwordReset.confirmPassword')}</label>
          <Input.Password
            id="confirm-password"
            placeholder={t('signin.passwordReset.confirmPasswordPlaceholder')}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full"
            size="large"
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
          {t('signin.passwordReset.submit')}
        </Button>
      </form>
    </div>
  );
}
