import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.db.schema import init_schema


if __name__ == "__main__":
    init_schema(get_settings())
    print("worktrace database schema initialized")
