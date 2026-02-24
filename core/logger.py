import logging
from core.config import LOG_FILE

def setup_logger():
    """Configura el sistema de logging para escribir en consola y en archivo."""
    logger = logging.getLogger("UnknownBot")
    logger.setLevel(logging.INFO)

    # Formato del log: Fecha - Nivel - Mensaje
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Handler para el ARCHIVO
    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)

    # Handler para la CONSOLA (reemplazará nuestros prints)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Evitar duplicados si se llama varias veces
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

# Instancia global para usar en todo el proyecto
bot_log = setup_logger()