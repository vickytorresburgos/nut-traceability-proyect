import logging


class _HealthCheckFilter(logging.Filter):
    """
    Filtra del access log de Uvicorn las requests a endpoints de health check.
    Esto evita que los healthchecks de Docker saturen los logs con entradas
    repetitivas que no aportan información durante el desarrollo.
    """
    _FILTERED_PATHS = {"/health", "/ocr/health"}

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(path in message for path in self._FILTERED_PATHS)


def configure_logging() -> None:
    """Aplica el filtro de health check al logger de acceso de Uvicorn."""
    logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())
