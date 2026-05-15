/**
 * SyncStatusBadge.tsx — Badge visual de estado de sincronización
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

type Status = 'PENDING' | 'SYNCED' | 'ERROR';

const CONFIG: Record<Status, { icon: string; label: string; bg: string; color: string }> = {
  SYNCED:  { icon: '', label: 'Sincronizado', bg: '#064e3b', color: '#34d399' },
  PENDING: { icon: '', label: 'Pendiente',    bg: '#422006', color: '#f59e0b' },
  ERROR:   { icon: '', label: 'Error',         bg: '#4c0519', color: '#f87171' },
};

export function SyncStatusBadge({ status }: { status: Status }) {
  const cfg = CONFIG[status] ?? CONFIG.PENDING;
  return (
    <View style={[styles.badge, { backgroundColor: cfg.bg }]}>
      <Text style={styles.icon}>{cfg.icon}</Text>
      <Text style={[styles.label, { color: cfg.color }]}>{cfg.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20 },
  icon: { fontSize: 12 },
  label: { fontSize: 11, fontWeight: '600' },
});
