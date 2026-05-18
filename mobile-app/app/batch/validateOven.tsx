import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, TextInput, TouchableOpacity, Image, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { db, NutBatch, Captura } from '../../src/db/database';
import { runOvenOcr } from '../../src/services/ocrApi';

export default function ValidateOvenScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [batch, setBatch] = useState<NutBatch | null>(null);
  const [captura, setCaptura] = useState<Captura | null>(null);
  const [loading, setLoading] = useState(true);

  const [ovenId, setOvenId] = useState('');
  const [humidity, setHumidity] = useState('');

  useEffect(() => {
    (async () => {
      const b = await db.getBatchById(id);
      const c = b ? await db.getCapturaByType(b.id, 'oven') : null;
      setBatch(b);
      setCaptura(c);

      if (b && c && !b.oven_id) {
        try {
          const ocrData = await runOvenOcr(c.local_path);

          const parsedOven = ocrData.oven_id ?? '';
          const parsedHumidity = ocrData.humidity ?? '';

          setOvenId(parsedOven);
          setHumidity(parsedHumidity);

          await db.updateBatchOven(b.id, parsedOven, parsedHumidity);

          if (ocrData.errors?.length) {
            Alert.alert(
              'Datos incompletos',
              ocrData.errors.join('\n'),
            );
          }
        } catch (err: any) {
          console.error('Error al ejecutar OCR Horno:', err);
          Alert.alert(
            'Error al leer el horno',
            err.message ?? 'No se pudo contactar al motor OCR.',
          );
        }
      } else if (b) {
        setOvenId(b.oven_id ?? '');
        setHumidity(b.humidity ?? '');
      }
      setLoading(false);
    })();
  }, [id]);

  const handleConfirm = async () => {
    if (!ovenId || !humidity) {
      Alert.alert('Datos incompletos', 'El OCR no detectó el horno o la humedad. Vuelva a tomar la foto.');
      return;
    }
    if (!batch || !captura) return;

    try {
      await db.updateBatchOven(id, ovenId, humidity);
      
      await db.enqueue(batch.id, 'ADD_OVEN', {
        oven_id: ovenId,
        humidity: humidity
      });

      router.navigate(`/camera?type=caliber&batchId=${id}`);
    } catch (err: any) {
      console.error('Error al encolar horno:', err);
      Alert.alert('Error', 'No se pudo guardar la información del horno localmente.');
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color="#34d399" size="large" />
        <Text style={{ color: '#34d399', marginTop: 16 }}>Procesando...</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}><Text style={styles.back}>← Volver</Text></TouchableOpacity>
        <Text style={styles.title}>Confirmar Horno</Text>
      </View>

      {captura && (
        <View style={styles.imageContainer}>
          <Image source={{ uri: captura.local_path }} style={styles.thumbnail} />
        </View>
      )}

      <View style={styles.warningBox}>
        <Text style={styles.warningText}>
          Revisá los datos. Si hay algún error, deberás volver a tomar la foto.
        </Text>
      </View>

      <View style={styles.form}>
        <Text style={styles.label}>Nº HORNO</Text>
        <TextInput style={[styles.input, { opacity: 0.8 }]} value={ovenId} editable={false} placeholder="No detectado" placeholderTextColor="#475569" />

        <Text style={styles.label}>HUMEDAD</Text>
        <TextInput style={[styles.input, { opacity: 0.8 }]} value={humidity} editable={false} placeholder="No detectada" placeholderTextColor="#475569" />
      </View>

      <View style={styles.actions}>
        <TouchableOpacity style={styles.btnSecondary} onPress={() => router.back()}>
          <Text style={styles.btnSecondaryText}>Retomar foto</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.btnPrimary} onPress={handleConfirm}>
          <Text style={styles.btnPrimaryText}>Confirmar</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  content: { padding: 20, paddingBottom: 40 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f172a' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, paddingTop: 20 },
  back: { color: '#34d399', fontSize: 15 },
  title: { color: '#f8fafc', fontSize: 18, fontWeight: '700' },
  imageContainer: { borderRadius: 16, overflow: 'hidden', marginBottom: 16, backgroundColor: '#1e293b' },
  thumbnail: { width: '100%', height: 180, resizeMode: 'cover' },
  warningBox: { backgroundColor: '#422006', borderLeftWidth: 3, borderLeftColor: '#f59e0b', padding: 12, borderRadius: 8, marginBottom: 20 },
  warningText: { color: '#fbbf24', fontSize: 13 },
  form: { gap: 12, marginBottom: 20 },
  label: { color: '#64748b', fontSize: 11, fontWeight: '600', letterSpacing: 1 },
  input: { backgroundColor: '#1e293b', color: '#f8fafc', padding: 14, borderRadius: 12, borderWidth: 1, borderColor: '#334155', fontSize: 15 },
  actions: { flexDirection: 'row', gap: 12 },
  btnSecondary: { flex: 1, padding: 16, borderRadius: 14, borderWidth: 1, borderColor: '#334155', alignItems: 'center' },
  btnSecondaryText: { color: '#94a3b8', fontWeight: '600' },
  btnPrimary: { flex: 1, padding: 16, borderRadius: 14, backgroundColor: '#059669', alignItems: 'center' },
  btnPrimaryText: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
