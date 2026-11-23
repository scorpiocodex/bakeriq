"""The Celery worker can only start if kombu accepts the installed redis-py.

celery[redis]==5.4.0 allows any kombu below 6 but caps redis-py below 6. kombu 5.7.0
started refusing redis-py older than 6.1.0, so a fresh image build resolved a pair that
cannot work together: the worker logged "Unrecoverable error: VersionMismatch" in a
loop while the container still showed as Up. Unit tests run tasks eagerly and never
open a broker connection, so nothing caught it. This does.
"""

import pytest
from kombu import Connection
from kombu.exceptions import VersionMismatch


def test_kombu_accepts_the_installed_redis_py():
    # Nothing listens on port 1: a refused connection is expected and fine. Only the
    # library's own version check (raised before any network traffic) is under test.
    connection = Connection("redis://127.0.0.1:1/0", connect_timeout=1)
    try:
        connection.ensure_connection(max_retries=0)
    except VersionMismatch as exc:
        pytest.fail(f"kombu and redis-py are incompatible: {exc}")
    except Exception:
        pass
    finally:
        connection.release()
