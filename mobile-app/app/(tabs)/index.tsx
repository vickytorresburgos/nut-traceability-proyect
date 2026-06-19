/**
 * app/(tabs)/index.tsx — Listado de Lotes del Día
 *
 * Muestra los lotes creados hoy con su estado de sincronización.
 * Se actualiza cada vez que la pantalla recibe foco.
 */

import React, { useCallback, useState } from 'react';
import {
  View, Text, FlatList, TouchableOpacity,
  RefreshControl, StyleSheet, StatusBar, Alert,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { db, NutBatch } from '../../src/db/database';
import { useAuth } from '../../src/context/AuthContext';
import { syncManager } from '../../src/services/syncManager';
import { BatchCard } from '../../src/components/BatchCard';

export default function LotesScreen() {
  const [lotes, setLotes] = useState<NutBatch[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const router = useRouter();
  const { username, logout } = useAuth();

  const load = useCallback(async () => {
    if (!username) return;
    const data = await db.getBatchesForUser(username);
    setLotes(data);
  }, [username]);

  // Recargar al volver a esta pantalla
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleRefresh = async () => {
    setRefreshing(true);
    await syncManager.sync();
    await load();
    setRefreshing(false);
  };

  const pendingCount = lotes.filter(l => l.status === 'PENDING').length;

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Historial de Lotes</Text>
          <Text style={styles.subtitle}>Operario: {username}</Text>
        </View>
        <TouchableOpacity
          style={styles.newBtn}
          onPress={() => router.push('/camera')}
        >
          <Text style={styles.newBtnText}>+ Nuevo</Text>
        </TouchableOpacity>
      </View>

      {/* Banner de pendientes */}
      {pendingCount > 0 && (
        <TouchableOpacity style={styles.syncBanner} onPress={handleRefresh}>
          <Text style={styles.syncBannerText}>
            {pendingCount} lote{pendingCount > 1 ? 's' : ''} pendiente{pendingCount > 1 ? 's' : ''} · Toca para sincronizar
          </Text>
        </TouchableOpacity>
      )}

      <FlatList
        data={lotes}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#34d399" />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No hay lotes registrados.</Text>
            <Text style={styles.emptyHint}>Tocá "+ Nuevo" para empezar.</Text>
          </View>
        }
        renderItem={({ item }) => (
          <BatchCard
            batch={item}
            onPress={() => {
              if (item.status === 'SYNCED' && item.trace_number) {
                router.push({ pathname: '/batch/qr', params: { id: item.id } });
              } else {
                router.push({ pathname: '/batch/validate', params: { id: item.id } });
              }
            }}
          />
        )}
      />

      <View style={styles.footer}>
        <TouchableOpacity onPress={logout} style={styles.logoutBtn}>
          <Text style={styles.logoutText}>Salir</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 60, paddingBottom: 16,
    borderBottomWidth: 1, borderBottomColor: '#1e293b',
  },
  title: { fontSize: 22, fontWeight: '700', color: '#f8fafc' },
  subtitle: { fontSize: 13, color: '#64748b', marginTop: 2 },
  newBtn: {
    backgroundColor: '#059669', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20,
  },
  newBtnText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  logoutBtn: {
    backgroundColor: '#334155', paddingHorizontal: 20, paddingVertical: 12, borderRadius: 12, alignItems: 'center',
  },
  logoutText: { color: '#94a3b8', fontSize: 14, fontWeight: '600' },
  syncBanner: {
    backgroundColor: '#422006', borderLeftWidth: 3, borderLeftColor: '#f59e0b',
    paddingHorizontal: 20, paddingVertical: 12,
  },
  syncBannerText: { color: '#fbbf24', fontSize: 13, fontWeight: '500' },
  list: { padding: 16, gap: 12 },
  empty: { alignItems: 'center', marginTop: 80 },
  emptyText: { color: '#94a3b8', fontSize: 16, fontWeight: '500' },
  emptyHint: { color: '#475569', fontSize: 13, marginTop: 6 },
  footer: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderTopWidth: 1,
    borderTopColor: '#1e293b',
    backgroundColor: '#0f172a'
  }
});
