/**
 * BatchCard.tsx — Tarjeta de lote con estado de sincronización
 */

import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { NutBatch } from '../db/database';
import { SyncStatusBadge } from './SyncStatusBadge';

interface Props {
  batch: NutBatch;
  onPress: () => void;
}

export function BatchCard({ batch, onPress }: Props) {
  const traceId = batch.trace_number ?? '—';
  const isProvisional = batch.server_id == null;

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.75}>
      <View style={styles.row}>
        <View style={styles.left}>
          <Text style={styles.traceId}>
            {traceId}
            {isProvisional && <Text style={styles.provisional}> (local)</Text>}
          </Text>
          <Text style={styles.farm}>{batch.farm_name ?? 'Sin finca'}</Text>
        </View>
        <SyncStatusBadge status={batch.status} />
      </View>

      <View style={styles.meta}>
        {batch.humidity && (
          <View style={styles.pill}>
            <Text style={styles.pillText}>Hum: {batch.humidity}</Text>
          </View>
        )}
        {batch.caliber && (
          <View style={styles.pill}>
            <Text style={styles.pillText}>Cal: {batch.caliber}</Text>
          </View>
        )}
        {batch.weight && (
          <View style={styles.pill}>
            <Text style={styles.pillText}>Peso: {batch.weight} kg</Text>
          </View>
        )}
        {batch.harvest_type && (
          <View style={[styles.pill, styles.pillHarvest]}>
            <Text style={styles.pillText}>
              {batch.harvest_type}
            </Text>
          </View>
        )}
      </View>

      {batch.status === 'PENDING' && (
        <Text style={styles.pendingHint}>Pendiente de sincronización →</Text>
      )}
      {batch.synced_at && (
        <Text style={styles.syncedHint}>
          Sincronizado {new Date(batch.synced_at).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })}
        </Text>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#1e293b', borderRadius: 16, padding: 16,
    borderWidth: 1, borderColor: '#334155',
  },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 },
  left: { flex: 1 },
  traceId: { color: '#f8fafc', fontSize: 18, fontWeight: '700', letterSpacing: 1 },
  provisional: { color: '#64748b', fontSize: 13, fontWeight: '400' },
  farm: { color: '#94a3b8', fontSize: 13, marginTop: 2 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  pill: { backgroundColor: '#0f172a', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20, borderWidth: 1, borderColor: '#334155' },
  pillHarvest: { borderColor: '#065f46' },
  pillText: { color: '#94a3b8', fontSize: 12 },
  pendingHint: { color: '#f59e0b', fontSize: 12, marginTop: 10 },
  syncedHint: { color: '#34d399', fontSize: 12, marginTop: 10 },
});
