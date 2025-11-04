import sys, os

# Ruta del proyecto en el servidor (se ajusta sola al directorio actual)
project_home = os.path.dirname(os.path.abspath(__file__))

if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Variables de entorno (ajusta SECRET_KEY en producción)
os.environ.setdefault("SECRET_KEY", "cambia_esto_por_un_valor_seguro")

# Importa la app de Flask como 'application' para Passenger
from app import app as application
