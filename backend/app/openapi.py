"""Print the API's OpenAPI spec, for the frontend's generated types (npm run types).

Built from the app object, so no server, database or model is needed.
"""

import json

from backend.app.api import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2, ensure_ascii=False))
