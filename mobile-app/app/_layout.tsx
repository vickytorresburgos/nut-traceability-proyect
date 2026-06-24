import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { db } from '../src/db/database';
import { syncManager } from '../src/services/syncManager';
import { AuthProvider, useAuth } from '../src/context/AuthContext';

function NavigationGuard({ children }: { children: React.ReactNode }) {
  const { token, isLoading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;

    const inAuthGroup = segments[0] === '(auth)';

    if (!token && !inAuthGroup) {
      // Redirect to login if not authenticated
      router.replace('/(auth)/login');
    } else if (token && inAuthGroup) {
      // Redirect to home if already authenticated
      router.replace('/');
    }
  }, [token, isLoading, segments]);

  return <>{children}</>;
}

export default function RootLayout() {
  const [isDbReady, setIsDbReady] = useState(false);

  useEffect(() => {
    async function init() {
      console.log("[RootLayout] Iniciando aplicación...");
      try {
        await db.open();
        setIsDbReady(true);
        syncManager.start();
      } catch (e) {
        console.error("[RootLayout] Error al inicializar DB:", e);
      }
    }
    init();
    return () => syncManager.stop();
  }, []);

  if (!isDbReady) return null;

  return (
    <AuthProvider>
      <NavigationGuard>
        <StatusBar style="light" />
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#0f172a' } }}>
          <Stack.Screen name="(auth)" options={{ headerShown: false }} />
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="batch/validate" />
          <Stack.Screen name="batch/qr" />
        </Stack>
      </NavigationGuard>
    </AuthProvider>
  );
}
