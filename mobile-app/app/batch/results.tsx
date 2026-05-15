import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator, Linking } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import QRCode from 'react-native-qrcode-svg';
import { db, NutBatch } from '../../src/db/database';
import { Platform } from 'react-native';
import { API_URL, DASHBOARD_URL } from '../../src/services/config';

export default function ResultsScreen() {
  const { trace_number } = useLocalSearchParams<{ trace_number: string }>();
  const router = useRouter();
  
  const [batch, setBatch] = useState<NutBatch | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      // Intentamos recuperar el batch usando la API local (TODO: en DB no tenemos el hash si no lo guardamos)
      // Como acabamos de llamar a createCompleteBatch, lo mejor es hacer un GET o simplemente
      // mostrar los datos guardados en SQLite. Para simplificar, buscamos en DB local:
      
      const batches = await db.getBatchesForToday();
      // Ojo, en validateCaliber guardamos en queue, pero no actualizamos el lote local con el trace_number del server
      // Lo ideal es tener un query por trace_number
      const b = batches.find(b => b.trace_number === trace_number);
      // Hack for now, wait a bit or use another method. Actually we need to fetch from server to get the hash!
      try {
        const response = await fetch(`${API_URL}/api/v1/batches/by-trace/${trace_number}`);
        if (response.ok) {
          const data = await response.json();
          setBatch(data);
        }
      } catch (e) {
        console.error(e);
      }
      
      setLoading(false);
    })();
  }, [trace_number]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#34d399" size="large" />
      </View>
    );
  }

  const qrUrl = `${DASHBOARD_URL}/?trace_id=${trace_number}`;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.title}>Lote Completado</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.label}>NÚMERO DE TRAZA</Text>
        <Text style={styles.valueLarge}>{trace_number}</Text>
      </View>

      {batch && (
        <>
          <View style={styles.card}>
            <Text style={styles.label}>FINCA</Text>
            <Text style={styles.value}>{batch.farm_name}</Text>
            <Text style={styles.label}>HUMEDAD</Text>
            <Text style={styles.value}>{batch.humidity}</Text>
            <Text style={styles.label}>CALIBRE</Text>
            <Text style={styles.value}>{batch.caliber}</Text>
            <Text style={styles.label}>PESO</Text>
            <Text style={styles.value}>{batch.weight}</Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.label}>HASH SHA-256</Text>
            <Text style={styles.hashText}>
              {(batch as any).sha256_hash || (batch as any).hash || 'No disponible'}
            </Text>
          </View>
        </>
      )}

      <TouchableOpacity style={styles.qrContainer} onPress={() => Linking.openURL(qrUrl)}>
        <QRCode
          value={qrUrl}
          size={200}
          backgroundColor="#ffffff"
          color="#0f172a"
        />
        <Text style={styles.qrHelp}>Escaneá o tocá para ver Dashboard</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.btnPrimary} onPress={() => router.replace('/(tabs)')}>
        <Text style={styles.btnPrimaryText}>Volver</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  content: { padding: 20, paddingBottom: 40, alignItems: 'center' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f172a' },
  header: { marginBottom: 24, paddingTop: 40 },
  title: { color: '#34d399', fontSize: 24, fontWeight: '700' },
  card: { backgroundColor: '#1e293b', width: '100%', padding: 20, borderRadius: 16, marginBottom: 16, borderWidth: 1, borderColor: '#334155' },
  label: { color: '#64748b', fontSize: 11, fontWeight: '600', letterSpacing: 1, marginBottom: 4, marginTop: 8 },
  value: { color: '#f8fafc', fontSize: 16, fontWeight: '500' },
  valueLarge: { color: '#f8fafc', fontSize: 32, fontWeight: '700', letterSpacing: 2 },
  hashText: { color: '#94a3b8', fontSize: 12, fontFamily: 'monospace' },
  qrContainer: { backgroundColor: '#fff', padding: 24, borderRadius: 24, alignItems: 'center', marginBottom: 32, width: '100%', elevation: 4, shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 10 },
  qrHelp: { color: '#059669', marginTop: 16, fontSize: 14, fontWeight: '700', textDecorationLine: 'underline' },
  btnPrimary: { width: '100%', padding: 18, borderRadius: 16, backgroundColor: '#059669', alignItems: 'center' },
  btnPrimaryText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
