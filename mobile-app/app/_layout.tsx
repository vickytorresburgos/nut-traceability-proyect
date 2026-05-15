import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { db } from '../src/db/database';
import { syncManager } from '../src/services/syncManager';

export default function RootLayout() {
  const [isDbReady, setIsDbReady] = useState(false);

  useEffect(() => {
    async function init() {
      console.log("[RootLayout] Iniciando aplicación...");
      console.log("[RootLayout] API URL:", process.env.EXPO_PUBLIC_API_URL || "Usando fallback");
      try {
        await db.open();
        console.log("[RootLayout] DB abierta correctamente");
        setIsDbReady(true);
        syncManager.start();
      } catch (e) {
        console.error("[RootLayout] Error al inicializar DB:", e);
      }
    }
    init();

    return () => syncManager.stop();
  }, []);

  if (!isDbReady) return null; // O mostrar SplashScreen

  return (
    <>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#0f172a' } }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="batch/validate" />
        <Stack.Screen name="batch/qr" />
      </Stack>
    </>
  );
}
