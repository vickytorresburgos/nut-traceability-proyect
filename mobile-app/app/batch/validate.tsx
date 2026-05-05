/**
 * app/batch/validate.tsx — Pantalla de Confirmación de Datos OCR (HU-04.01 / 04.02)
 *
 * Flujo:
 *  1. Recibe `id` del lote local (NutBatch.id)
 *  2. Carga el lote + captura del remito
 *  3. Muestra formulario pre-poblado con datos OCR (editables)
 *  4. Al confirmar: encola operación en sync_queue y vuelve al listado
 */

import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  Image, StyleSheet, Alert, ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { db, NutBatch, Captura } from '../../src/db/database';
import { SyncStatusBadge } from '../../src/components/SyncStatusBadge';
import { generateLocalTraceNumber } from '../../src/services/traceGenerator';

const KNOWN_FARMS = [
  'LOS TILOS', 'LAS FLORES', 'LOS ANDES', 'LOS CAPOS',
  'LA ESPERANZA', 'LA CABAÑA', 'LAS PEPAS',
];

export default function ValidateScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [batch, setBatch] = useState<NutBatch | null>(null);
  const [captura, setCaptura] = useState<Captura | null>(null);
  const [loading, setLoading] = useState(true);

  // Campos editables
  const [farmName, setFarmName] = useState('');
  const [harvestType, setHarvestType] = useState<'manual' | 'mecanica'>('mecanica');
  const [date, setDate] = useState('');

  useEffect(() => {
    (async () => {
      const b = await db.getBatchById(id);
      const c = b ? await db.getCapturaByType(b.id, 'remito') : null;
      setBatch(b);
      setCaptura(c);
      
      if (b && c && b.farm_name === '') {
        // Ejecutar OCR llamando al servicio local (solo en desarrollo / si hay conexión)
        try {
          const form = new FormData();
          form.append('image', {
            uri: c.local_path,
            name: 'remito.jpg',
            type: 'image/jpeg',
          } as any);

          const apiBase = process.env.EXPO_PUBLIC_API_URL ?? 'http://192.168.100.10:8080';
          const ocrUrl = apiBase.replace(':8080', ':8082') + '/ocr/remito';

          const res = await fetch(ocrUrl, { method: 'POST', body: form });
          if (!res.ok) throw new Error('Error en OCR');

          const ocrData = await res.json();
          const fName = ocrData.farm_name ?? '';
          const hType = ocrData.harvest_type ?? 'mecanica';
          const parsedDate = ocrData.date ?? '';

          setFarmName(fName);
          setHarvestType(hType);
          setDate(parsedDate);

          // Actualizar la DB local para que no vuelva a correr el OCR si el operario sale y entra
          await db.updateBatchDetails(b.id, fName, hType, parsedDate, b.trace_number || '');

        } catch (err: any) {
          console.error("Error al ejecutar OCR:", err);
          Alert.alert('Error de Conexión', `No se pudo contactar al motor OCR. Verificá que estés conectado a la red local.\nDetalle: ${err.message}`);
        }
      } else if (b) {
        setFarmName(b.farm_name ?? '');
        setHarvestType((b.harvest_type as 'manual' | 'mecanica') ?? 'mecanica');
        setDate(b.remito_date ?? '');
      }
      setLoading(false);
    })();
  }, [id]);

  const handleConfirm = async () => {
    if (!farmName.trim()) {
      Alert.alert('Finca no detectada', 'No se detectó el nombre de la finca. Por favor, vuelva a tomar la foto.');
      return;
    }
    if (!KNOWN_FARMS.includes(farmName.toUpperCase())) {
      Alert.alert(
        'Finca no reconocida',
        `"${farmName}" no está en la lista autorizada. ¿Confirmar de todas formas?`,
        [
          { text: 'Cancelar', style: 'cancel' },
          { text: 'Confirmar', onPress: () => save() },
        ]
      );
      return;
    }
    await save();
  };

  const save = async () => {
    if (!batch) return;
    
    // Generar el trace number local definitivo basado en la finca seleccionada
    const finalTraceNumber = await generateLocalTraceNumber(farmName.toUpperCase());

    // Actualizar en SQLite local
    await db.updateBatchDetails(batch.id, farmName.toUpperCase(), harvestType, date, finalTraceNumber);

    // Encolar sincronización con el servidor
    await db.enqueue(batch.id, 'CREATE_BATCH', {
      farm_name: farmName.toUpperCase(),
      harvest_type: harvestType,
      remito_date: date,
    });

    // Avanzar a la captura del horno pasando el ID del lote
    router.replace({ pathname: '/camera', params: { type: 'oven', batchId: batch.id } });
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
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.back}>← Volver</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Confirmar Datos</Text>
        <SyncStatusBadge status={batch?.status ?? 'PENDING'} />
      </View>

      {/* Miniatura de la foto */}
      {captura && (
        <View style={styles.imageContainer}>
          <Image source={{ uri: captura.local_path }} style={styles.thumbnail} />
          {captura.ocr_confidence != null && (
            <View style={styles.confidenceBar}>
              <Text style={styles.confidenceLabel}>
                Confianza OCR: {captura.ocr_confidence.toFixed(0)}%
              </Text>
              <View style={styles.barBg}>
                <View style={[styles.barFill, { width: `${captura.ocr_confidence}%` as any }]} />
              </View>
            </View>
          )}
        </View>
      )}

      {/* Aviso */}
      <View style={styles.warningBox}>
        <Text style={styles.warningText}>
          Revisá los datos obtenidos por el escáner antes de guardar. Si hay algún error, deberás volver a tomar la foto.
        </Text>
      </View>

      {/* Formulario */}
      <View style={styles.form}>
        {/* Finca */}
        <Text style={styles.label}>FINCA</Text>
        <View style={styles.pickerWrap}>
          {farmName ? (
            <View style={[styles.chip, styles.chipActive]}>
              <Text style={[styles.chipText, styles.chipTextActive]}>
                {farmName.toUpperCase()}
              </Text>
            </View>
          ) : (
            <Text style={styles.errorText}>No detectada</Text>
          )}
        </View>

        {/* Tipo de cosecha */}
        <Text style={styles.label}>TIPO DE COSECHA</Text>
        <View style={styles.row}>
          {(['mecanica', 'manual'] as const).map((t) => (
            <View
              key={t}
              style={[styles.toggle, harvestType === t && styles.toggleActive, harvestType !== t && { opacity: 0.5 }]}
            >
              <Text style={[styles.toggleText, harvestType === t && styles.toggleTextActive]}>
                {t === 'mecanica' ? 'Mecánica' : 'Manual'}
              </Text>
            </View>
          ))}
        </View>

        {/* Fecha */}
        <Text style={styles.label}>FECHA</Text>
        <TextInput
          style={[styles.input, { opacity: 0.8 }]}
          value={date}
          editable={false}
          placeholder="No detectada"
          placeholderTextColor="#475569"
        />
      </View>

      {/* Estado de conexión */}
      <View style={styles.offlineBanner}>
        <Text style={styles.offlineText}>
          Los datos se guardarán localmente y se sincronizarán al recuperar conexión.
        </Text>
      </View>

      {/* Botones */}
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
  confidenceBar: { padding: 12 },
  confidenceLabel: { color: '#94a3b8', fontSize: 12, marginBottom: 6 },
  barBg: { height: 6, backgroundColor: '#334155', borderRadius: 3 },
  barFill: { height: 6, backgroundColor: '#34d399', borderRadius: 3 },
  warningBox: { backgroundColor: '#422006', borderLeftWidth: 3, borderLeftColor: '#f59e0b', padding: 12, borderRadius: 8, marginBottom: 20 },
  warningText: { color: '#fbbf24', fontSize: 13 },
  form: { gap: 12, marginBottom: 20 },
  label: { color: '#64748b', fontSize: 11, fontWeight: '600', letterSpacing: 1 },
  pickerWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155' },
  chipActive: { backgroundColor: '#065f46', borderColor: '#34d399' },
  chipText: { color: '#94a3b8', fontSize: 12 },
  chipTextActive: { color: '#34d399', fontWeight: '600' },
  row: { flexDirection: 'row', gap: 12 },
  toggle: { flex: 1, padding: 14, borderRadius: 12, backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155', alignItems: 'center' },
  toggleActive: { backgroundColor: '#065f46', borderColor: '#34d399' },
  toggleText: { color: '#94a3b8', fontWeight: '500' },
  toggleTextActive: { color: '#34d399', fontWeight: '700' },
  input: { backgroundColor: '#1e293b', color: '#f8fafc', padding: 14, borderRadius: 12, borderWidth: 1, borderColor: '#334155', fontSize: 15 },
  offlineBanner: { backgroundColor: '#1c1917', borderRadius: 12, padding: 14, marginBottom: 24 },
  offlineText: { color: '#a16207', fontSize: 13 },
  actions: { flexDirection: 'row', gap: 12 },
  btnSecondary: { flex: 1, padding: 16, borderRadius: 14, borderWidth: 1, borderColor: '#334155', alignItems: 'center' },
  btnSecondaryText: { color: '#94a3b8', fontWeight: '600' },
  btnPrimary: { flex: 1, padding: 16, borderRadius: 14, backgroundColor: '#059669', alignItems: 'center' },
  btnPrimaryText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  errorText: { color: '#ef4444', fontSize: 14, fontStyle: 'italic', paddingVertical: 6 },
});
