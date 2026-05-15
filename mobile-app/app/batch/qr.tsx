/**
 * app/batch/qr.tsx — Pantalla de QR del Lote (HU-04.04)
 *
 * Muestra el QR generado localmente con la URL del dashboard público.
 * Funciona 100% offline — el QR se genera en cliente con react-native-qrcode-svg.
 */

import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  StyleSheet, Share, ActivityIndicator, Linking,
} from 'react-native';
import QRCode from 'react-native-qrcode-svg';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { db, NutBatch } from '../../src/db/database';
import { DASHBOARD_URL } from '../../src/services/config';

export default function QRScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [batch, setBatch] = useState<NutBatch | null>(null);

  useEffect(() => {
    db.getBatchById(id).then(setBatch);
  }, [id]);

  if (!batch) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#34d399" size="large" />
      </View>
    );
  }

  const traceId = batch.trace_number ?? batch.id.slice(0, 8).toUpperCase();
  const qrUrl = `${DASHBOARD_URL}/?trace_id=${traceId}`;
  const isProvisional = batch.server_id == null;

  const handleShare = async () => {
    await Share.share({ message: `Lote ${traceId}\n${qrUrl}` });
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.back}>←</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Código QR del Lote</Text>
        <View style={{ width: 32 }} />
      </View>

      {/* Trace ID */}
      <View style={styles.traceBox}>
        <Text style={styles.traceLabel}>Número de Traza</Text>
        <Text style={styles.traceId}>{traceId}</Text>
        {isProvisional && (
          <View style={styles.provisionalBadge}>
            <Text style={styles.provisionalText}>ID provisional — sincronizará pronto</Text>
          </View>
        )}
      </View>

      {/* QR */}
      <View style={styles.qrContainer}>
        <QRCode
          value={qrUrl}
          size={220}
          color="#0f172a"
          backgroundColor="#ffffff"
          ecl="H"
        />
      </View>
      <TouchableOpacity onPress={() => Linking.openURL(qrUrl)}>
        <Text style={styles.qrUrl}>{qrUrl}</Text>
      </TouchableOpacity>

      {/* Resumen del lote */}
      <View style={styles.summary}>
        <Row label="Finca" value={batch.farm_name ?? '—'} />
        <Row label="Cosecha" value={batch.harvest_type ?? '—'} />
        <Row label="Fecha" value={batch.remito_date ?? '—'} />
        <Row label="Humedad" value={batch.humidity ?? '—'} highlight />
        <Row label="Calibre" value={batch.caliber ?? '—'} />
        <Row label="Peso" value={batch.weight ?? '—'} />
      </View>

      {/* Hash */}
      {batch.sha256_hash && (
        <View style={styles.hashBox}>
          <Text style={styles.hashLabel}>Sello SHA-256</Text>
          <Text style={styles.hashValue} numberOfLines={2}>{batch.sha256_hash}</Text>
        </View>
      )}

      {/* Acciones */}
      <TouchableOpacity style={styles.shareBtn} onPress={handleShare}>
        <Text style={styles.shareBtnText}>↑ Compartir</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function Row({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <View style={rowStyles.row}>
      <Text style={rowStyles.label}>{label}</Text>
      <Text style={[rowStyles.value, highlight && rowStyles.highlight]}>{value}</Text>
    </View>
  );
}

const rowStyles = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  label: { color: '#64748b', fontSize: 14 },
  value: { color: '#f8fafc', fontSize: 14, fontWeight: '500' },
  highlight: { color: '#34d399', fontWeight: '700' },
});

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  content: { padding: 20, paddingBottom: 40 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f172a' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 20, marginBottom: 24 },
  back: { color: '#34d399', fontSize: 22 },
  title: { color: '#f8fafc', fontSize: 18, fontWeight: '700' },
  traceBox: { alignItems: 'center', marginBottom: 24 },
  traceLabel: { color: '#64748b', fontSize: 12, letterSpacing: 1 },
  traceId: { color: '#fff', fontSize: 44, fontWeight: '800', letterSpacing: 4, marginTop: 4 },
  provisionalBadge: { backgroundColor: '#422006', paddingHorizontal: 12, paddingVertical: 4, borderRadius: 20, marginTop: 8 },
  provisionalText: { color: '#fbbf24', fontSize: 12 },
  qrContainer: { alignItems: 'center', backgroundColor: '#fff', padding: 20, borderRadius: 24, marginBottom: 12, shadowColor: '#34d399', shadowOpacity: 0.3, shadowRadius: 20, elevation: 8 },
  qrUrl: { textAlign: 'center', color: '#34d399', fontSize: 11, marginBottom: 24, textDecorationLine: 'underline' },
  summary: { backgroundColor: '#1e293b', borderRadius: 16, padding: 16, marginBottom: 16 },
  hashBox: { backgroundColor: '#0a0a1a', borderWidth: 1, borderColor: '#1e293b', borderRadius: 12, padding: 14, marginBottom: 24 },
  hashLabel: { color: '#475569', fontSize: 11, marginBottom: 6, letterSpacing: 0.5 },
  hashValue: { color: '#334155', fontFamily: 'monospace', fontSize: 11, lineHeight: 18 },
  shareBtn: { backgroundColor: '#0f4c81', padding: 16, borderRadius: 14, alignItems: 'center' },
  shareBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
