import os
USE_SAP_PY_JWT = os.getenv('USE_SAP_PY_JWT', 'false').lower() == 'true'
