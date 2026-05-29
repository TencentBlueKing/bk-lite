'use client';

import React, { createContext, useContext } from 'react';

interface AuthContextType {
  token: string | null;
  isAuthenticated: boolean;
  isCheckingAuth: boolean;
}

const AuthContext = createContext<AuthContextType | null>({
  token: 'mock-token',
  isAuthenticated: true,
  isCheckingAuth: false,
});

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    return { token: 'mock-token', isAuthenticated: true, isCheckingAuth: false };
  }
  return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AuthContext.Provider value={{ token: 'mock-token', isAuthenticated: true, isCheckingAuth: false }}>
    {children}
  </AuthContext.Provider>
);

export default AuthProvider;
