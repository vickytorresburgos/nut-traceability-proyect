CONFIDENCE_REJECT_THRESHOLD = 20.0   # umbral para rechazar con HTTP 400 (imagen ilegible)
CONFIDENCE_WARN_THRESHOLD   = 30.0   # umbral para activar confidence_alert en la app
                                      # Remitos con tinta manuscrita violeta puntúan 55-65%
                                      # (límite real de Tesseract para ese tipo de tinta),
                                      # no es baja calidad — no debe disparar la alerta.

KNOWN_FARMS = [
    'LOS TILOS', 'LAS FLORES', 'LOS ANDES', 'LOS CAPOS',
    'LA ESPERANZA', 'LA CABAÑA', 'LAS PEPAS'
]

CALIBER_SIZES = ['28', '28-30', '30-32', '32-34', '34-36', '36+']

HUMIDITY_MIN = 3.5
HUMIDITY_MAX = 5.5

OVEN_ID_MIN = 1
OVEN_ID_MAX = 32

MESES_ES = {
    'enero': '01', 'febrero': '02', 'marzo': '03', 'abril': '04',
    'mayo': '05', 'junio': '06', 'julio': '07', 'agosto': '08',
    'septiembre': '09', 'octubre': '10', 'noviembre': '11', 'diciembre': '12'
}
