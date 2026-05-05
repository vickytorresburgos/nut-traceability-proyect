import { Tabs } from 'expo-router';
import React from 'react';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: '#1e293b',
          borderTopColor: '#334155',
        },
        tabBarActiveTintColor: '#34d399',
        tabBarInactiveTintColor: '#64748b',
      }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Lotes',
          tabBarIcon: () => <></>, // Simplificado para no requerir expo/vector-icons
        }}
      />
      <Tabs.Screen
        name="camera"
        options={{
          title: 'Cámara',
          tabBarIcon: () => <></>,
        }}
      />
    </Tabs>
  );
}
