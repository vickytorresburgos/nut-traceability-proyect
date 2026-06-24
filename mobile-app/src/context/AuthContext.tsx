import React, { createContext, useContext, useState, useEffect } from 'react';
import * as SecureStore from 'expo-secure-store';
import { useRouter, useSegments } from 'expo-router';

interface AuthContextType {
  token: string | null;
  username: string | null;
  isLoading: boolean;
  login: (username: string, token: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    loadStorageData();
  }, []);

  async function loadStorageData() {
    try {
      const storedToken = await SecureStore.getItemAsync('userToken');
      const storedUser = await SecureStore.getItemAsync('userName');
      if (storedToken) setToken(storedToken);
      if (storedUser) setUsername(storedUser);
    } catch (e) {
      console.error('Error loading auth data', e);
    } finally {
      setIsLoading(false);
    }
  }

  async function login(newUser: string, newToken: string) {
    setToken(newToken);
    setUsername(newUser);
    await SecureStore.setItemAsync('userToken', newToken);
    await SecureStore.setItemAsync('userName', newUser);
  }

  async function logout() {
    setToken(null);
    setUsername(null);
    await SecureStore.deleteItemAsync('userToken');
    await SecureStore.deleteItemAsync('userName');
  }

  return (
    <AuthContext.Provider value={{ token, username, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
