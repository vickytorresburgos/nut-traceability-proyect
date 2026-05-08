/**
 * app/(tabs)/camera.tsx — Captura de Remitos y Displays (HU-04.01)
 *
 * Utiliza Expo Camera (SDK 51+ con <CameraView>).
 * Guarda la captura temporal y delega en database.ts para calcular SHA-256
 * y guardarla en FileSystem.
 */

import React, { useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRouter, useGlobalSearchParams } from 'expo-router';
import { db } from '../../src/db/database';
import { generateLocalTraceNumber } from '../../src/services/traceGenerator';

export default function CameraScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const router = useRouter();

  const params = useGlobalSearchParams<{ type?: 'remito' | 'oven' | 'caliber', batchId?: string }>();
  
  // Estados
  const [type, setType] = useState<'remito' | 'oven' | 'caliber'>('remito');
  const [isProcessing, setIsProcessing] = useState(false);
  const [flashOn, setFlashOn] = useState(false);
  const activeBatchId = useRef<string | null>(null);

  // Sincronizar params con el estado
  React.useEffect(() => {
    if (params.type) setType(params.type);
    if (params.batchId) activeBatchId.current = params.batchId;
  }, [params.type, params.batchId]);

  if (!permission) return <View style={styles.center} />;

  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.text}>Necesitamos tu permiso para usar la cámara</Text>
        <TouchableOpacity style={styles.btnPrimary} onPress={requestPermission}>
          <Text style={styles.btnPrimaryText}>Otorgar permiso</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const takePicture = async () => {
    if (!cameraRef.current || isProcessing) return;
    
    setIsProcessing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 1, // Calidad máxima para el OCR
        base64: false, // Guardamos la URI y lo pasamos al file system
      });

      if (!photo) throw new Error('No se pudo capturar la foto');

      // 1. Crear el lote si es un remito (inicio de trazabilidad)
      // O pedir ID de lote activo si es horno/calibre (simplificado: asumimos lote nuevo para el remito)
      let batchId: string;

      if (type === 'remito') {
        // trace_number se asigna en Validate una vez que el OCR confirma la finca.
        // Se deja NULL para evitar colisiones UNIQUE antes de conocer los datos reales.
        const batch = await db.createBatch({
          trace_number: null,
          farm_name: '',
          harvest_type: 'mecanica',
          remito_date: new Date().toISOString().slice(0, 10),
        });
        batchId = batch.id;
      } else {
        if (!activeBatchId.current) {
          Alert.alert('Error', 'Seleccioná un lote desde el listado para agregar la captura de horno o calibre.');
          setIsProcessing(false);
          return;
        }
        batchId = activeBatchId.current;
      }

      // 2. Guardar captura (calcula SHA-256 internamente)
      await db.saveCaptura(batchId, type, photo.uri);

      // 3. Ir a la validación correspondiente
      if (type === 'remito') {
        router.push({ pathname: '/batch/validate', params: { id: batchId } });
      } else if (type === 'oven') {
        router.push({ pathname: '/batch/validateOven', params: { id: batchId } });
      } else if (type === 'caliber') {
        router.push({ pathname: '/batch/validateCaliber', params: { id: batchId } });
      }

    } catch (err: any) {
      Alert.alert('Error al capturar', err.message);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* Opciones de tipo de captura */}
      <View style={styles.typeSelector}>
        <TouchableOpacity 
          style={[styles.typeBtn, type === 'remito' && styles.typeBtnActive]}
          onPress={() => setType('remito')}
        >
          <Text style={[styles.typeText, type === 'remito' && styles.typeTextActive]}>Remito</Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={[styles.typeBtn, type === 'oven' && styles.typeBtnActive]}
          onPress={() => setType('oven')}
        >
          <Text style={[styles.typeText, type === 'oven' && styles.typeTextActive]}>Humedad</Text>
        </TouchableOpacity>
        <TouchableOpacity 
          style={[styles.typeBtn, type === 'caliber' && styles.typeBtnActive]}
          onPress={() => setType('caliber')}
        >
          <Text style={[styles.typeText, type === 'caliber' && styles.typeTextActive]}>Calibre</Text>
        </TouchableOpacity>
      </View>

      {/* Botón de Flash */}
      <TouchableOpacity 
        style={styles.flashBtn} 
        onPress={() => setFlashOn(!flashOn)}
      >
        <Text style={styles.flashText}>FLASH {flashOn ? 'ON' : 'OFF'}</Text>
      </TouchableOpacity>

      <CameraView 
        style={styles.camera} 
        facing="back"
        enableTorch={flashOn}
        // @ts-ignore - expo-camera CameraView missing ref in its types
        ref={cameraRef}
      />

      {/* Overlay: Sibling de CameraView con absolute positioning (SDK 51/54) */}
      <View style={[styles.overlay, StyleSheet.absoluteFillObject]} pointerEvents="box-none">
        {/* Rectángulo guía para OCR */}
        <View style={styles.guideFrame} />
        <Text style={styles.guideText}>
          Alineá el {type === 'remito' ? 'remito' : type === 'oven' ? 'display del horno' : 'papel del calibre'} dentro del marco
        </Text>

        {/* Botón de captura */}
        <View style={styles.controls}>
          {isProcessing ? (
            <ActivityIndicator size="large" color="#34d399" />
          ) : (
            <TouchableOpacity style={styles.captureBtn} onPress={takePicture}>
              <View style={styles.captureInner} />
            </TouchableOpacity>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#0f172a' },
  text: { color: '#f8fafc', marginBottom: 20, fontSize: 16 },
  camera: { flex: 1 },
  overlay: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  guideFrame: { width: '85%', height: '60%', borderWidth: 2, borderColor: '#34d399', borderRadius: 16, backgroundColor: 'rgba(0,0,0,0.1)' },
  guideText: { color: '#fff', fontSize: 14, fontWeight: '500', marginTop: 20, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  controls: { position: 'absolute', bottom: 40, width: '100%', alignItems: 'center' },
  captureBtn: { width: 72, height: 72, borderRadius: 36, backgroundColor: 'rgba(255,255,255,0.3)', justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: '#fff' },
  captureInner: { width: 60, height: 60, borderRadius: 30, backgroundColor: '#fff' },
  typeSelector: { position: 'absolute', top: 50, left: 0, right: 0, zIndex: 10, flexDirection: 'row', justifyContent: 'center', gap: 12, paddingHorizontal: 20 },
  typeBtn: { backgroundColor: 'rgba(15, 23, 42, 0.8)', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20, borderWidth: 1, borderColor: '#334155' },
  typeBtnActive: { backgroundColor: '#065f46', borderColor: '#34d399' },
  typeText: { color: '#94a3b8', fontSize: 14, fontWeight: '600' },
  typeTextActive: { color: '#34d399' },
  btnPrimary: { backgroundColor: '#059669', paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12 },
  btnPrimaryText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  flashBtn: { position: 'absolute', top: 50, right: 20, zIndex: 10, backgroundColor: 'rgba(15, 23, 42, 0.8)', paddingHorizontal: 12, paddingVertical: 10, borderRadius: 20, borderWidth: 1, borderColor: '#334155' },
  flashText: { color: '#f8fafc', fontSize: 14, fontWeight: '600' },
});
