"use client";
import { useState } from "react";
import { Input, Button } from "antd";

interface LoginResponse {
  temporary_pwd?: boolean;
  enable_otp?: boolean;
  qrcode?: boolean;
  token?: string;
  username?: string;
  id?: string;
  locale?: string;
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

  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (newPassword !== confirmPassword) {
      onError("Passwords do not match");
      return;
    }
    
    if (newPassword.length < 8) {
      onError("Password must be at least 8 characters long");
      return;
    }
    
    setIsLoading(true);
    onError("");
    
    try {
      const response = await fetch('/api/proxy/core/api/reset_pwd/', {
        method: "POST",
        headers: { 
          "Content-Type": "application/json" 
        },
        body: JSON.stringify({
          username: loginData.username,
          password: newPassword
        }),
      });
      
      const responseData = await response.json();
      
      if (!response.ok || !responseData.result) {
        onError(responseData.message || "Password reset failed");
        setIsLoading(false);
        return;
      }
      
      // Update login data to remove temporary_pwd flag
      const updatedLoginData = { ...loginData, temporary_pwd: false };
      onPasswordReset(updatedLoginData);
      
    } catch (error) {
      console.error("Error resetting password:", error);
      onError(error instanceof Error ? error.message : "An unknown error occurred");
      setIsLoading(false);
    }
  };

  return (
    <div>
      <div className="text-center mb-6">
        <h3 className="text-xl font-semibold text-[var(--color-text-1)]">Reset</h3>
        <p className="text-gray-500 mt-2">You are using a temporary password. Please create a new password to continue.</p>
      </div>
      
      <form onSubmit={handlePasswordReset} className="flex flex-col space-y-6 w-full">
        <div className="space-y-2">
          <label htmlFor="username-display" className="text-sm font-medium text-[var(--color-text-1)]">Username</label>
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
          <label htmlFor="new-password" className="text-sm font-medium text-[var(--color-text-1)]">New Password</label>
          <Input.Password
            id="new-password"
            placeholder="Enter new password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full"
            size="large"
            required
          />
        </div>
        
        <div className="space-y-2">
          <label htmlFor="confirm-password" className="text-sm font-medium text-[var(--color-text-1)]">Confirm Password</label>
          <Input.Password
            id="confirm-password"
            placeholder="Confirm new password"
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
          Reset Password
        </Button>
      </form>
    </div>
  );
}