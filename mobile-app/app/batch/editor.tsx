import React, { useState } from 'react';
import { View, Text, StyleSheet, Image, TouchableOpacity, ActivityIndicator, Alert } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ImageManipulator from 'expo-image-manipulator';
import { db } from '../../src/db/database';

/**
 * Pantalla de edición manual de imagen (Paso intermedio post-captura)
 * 
 * Permite al operario rotar la imagen para asegurar que el texto esté horizontal
 * y bien encuadrado antes de enviarlo al motor OCR.
 */
export default function ImageEditorScreen() {
  const { uri, batchId, type } = useLocalSearchParams<{ uri: string, batchId: string, type: 'remito' | 'oven' | 'caliber' }>();
  const router = useRouter();

  const [isProcessing, setIsProcessing] = useState(false);
  const [rotation, setRotation] = useState(0);

  const handleRotate = () => {
    // Incrementamos la rotación en pasos de 90 grados
    setRotation((prev) => (prev + 90) % 360);
  };

  const handleConfirm = async () => {
    if (isProcessing) return;
    setIsProcessing(true);
    
    try {
      console.log(`[Editor] Procesando imagen: rotación=${rotation}°, tipo=${type}`);
      
      // Aplicamos la rotación físicamente a los píxeles
      // Esto genera una nueva imagen 'upright' (vertical o horizontal según la rotación elegida)
      // sin depender de metadatos EXIF que se pierden luego.
      const result = await ImageManipulator.manipulateAsync(
        uri,
        rotation !== 0 ? [{ rotate: rotation }] : [],
        { compress: 1, format: ImageManipulator.SaveFormat.JPEG }
      );

      // Persistimos la captura FINAL en la base de datos local
      // saveCaptura calcula el hash SHA-256 e inicia la integridad local.
      await db.saveCaptura(batchId, type, result.uri);

      // Navegamos a la validación correspondiente
      if (type === 'remito') {
        router.replace({ pathname: '/batch/validate', params: { id: batchId } });
      } else if (type === 'oven') {
        router.replace({ pathname: '/batch/validateOven', params: { id: batchId } });
      } else if (type === 'caliber') {
        router.replace({ pathname: '/batch/validateCaliber', params: { id: batchId } });
      }
    } catch (err: any) {
      console.error('[Editor] Error:', err);
      Alert.alert('Error', 'No se pudo procesar la imagen. Intente nuevamente.');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Ajustar Imagen</Text>
        <Text style={styles.subtitle}>Asegurá que el texto esté horizontal y bien alineado.</Text>
      </View>

      <View style={styles.previewWrapper}>
        <View style={styles.previewContainer}>
          <Image 
            source={{ uri }} 
            style={[
              styles.preview, 
              { transform: [{ rotate: `${rotation}deg` }] }
            ]} 
            resizeMode="contain"
          />
        </View>
      </View>

      <View style={styles.footer}>
        <View style={styles.actions}>
          <TouchableOpacity 
            style={styles.btnSecondary} 
            onPress={handleRotate}
            disabled={isProcessing}
          >
            <Text style={styles.btnSecondaryText}>Rotar 90°</Text>
          </TouchableOpacity>

          <TouchableOpacity 
            style={[styles.btnPrimary, isProcessing && { opacity: 0.6 }]} 
            onPress={handleConfirm}
            disabled={isProcessing}
          >
            {isProcessing ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.btnPrimaryText}>Confirmar</Text>
            )}
          </TouchableOpacity>
        </View>
        
        <TouchableOpacity 
          style={styles.btnGhost} 
          onPress={() => router.back()}
          disabled={isProcessing}
        >
          <Text style={styles.btnGhostText}>Retomar Foto</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a', padding: 20 },
  header: { marginTop: 40, marginBottom: 24, alignItems: 'center' },
  title: { color: '#f8fafc', fontSize: 24, fontWeight: '800' },
  subtitle: { color: '#94a3b8', fontSize: 15, marginTop: 6, textAlign: 'center', lineHeight: 22 },
  previewWrapper: { flex: 1, paddingVertical: 10 },
  previewContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#1e293b', borderRadius: 24, overflow: 'hidden', borderWidth: 1, borderColor: '#334155' },
  preview: { width: '90%', height: '90%' },
  footer: { marginTop: 24, paddingBottom: 20 },
  actions: { flexDirection: 'row', gap: 12, marginBottom: 16 },
  btnPrimary: { flex: 2, backgroundColor: '#059669', padding: 20, borderRadius: 16, alignItems: 'center', justifyContent: 'center', elevation: 2 },
  btnPrimaryText: { color: '#fff', fontWeight: '800', fontSize: 16 },
  btnSecondary: { flex: 1, backgroundColor: '#334155', padding: 20, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#475569' },
  btnSecondaryText: { color: '#f8fafc', fontWeight: '700', fontSize: 15 },
  btnGhost: { alignItems: 'center', padding: 12 },
  btnGhostText: { color: '#64748b', fontSize: 15, fontWeight: '600', textDecorationLine: 'underline' },
});
