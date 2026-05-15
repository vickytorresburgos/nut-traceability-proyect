import logging


class _HealthCheckFilter(logging.Filter):
    """
    Filtra del access log de Uvicorn las requests al endpoint de health check.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        return "/ocr/health" not in record.getMessage()


def configure_logging() -> None:
    """Aplica el filtro al logger de acceso de Uvicorn."""
    logging.getLogger("uvicorn.access").addFilter(_HealthCheckFilter())
