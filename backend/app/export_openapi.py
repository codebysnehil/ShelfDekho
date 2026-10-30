"""Write the OpenAPI schema to a file so the frontend can generate TypeScript types.

python -m app.export_openapi ../frontend/openapi.json
"""

import json
import os
import sys

os.environ.setdefault("ENVIRONMENT", "test")  # no DB connection is made

from app.main import app  # noqa: E402

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    # Force LF so the file is byte-identical on Windows and Linux (CI diffs it).
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        json.dump(app.openapi(), f, indent=2)
        f.write("\n")
    print(f"wrote {target}")
