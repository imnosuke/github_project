from io import BytesIO
from unittest.mock import Mock

import pytest

from apps.streamlit.data import clickhouse_http
from apps.streamlit.data.config import ClickHouseConfig


@pytest.mark.parametrize(("status", "body", "error"), [
    (403, b"details must stay private\n", "HTTP 403"),
    (200, b'{"x":1}\nquery failure\n', "invalid query response"),
    (200, b'{"x":1}', "HTTPException"),
])
def test_transport_redacts_errors_and_preserves_status(monkeypatch, status, body, error):
    response = BytesIO(body)
    response.status = status
    connection = Mock()
    connection.getresponse.return_value = response
    monkeypatch.setattr(clickhouse_http, "HTTPSConnection", lambda *_args, **_kwargs: connection)

    with pytest.raises(OSError, match=error) as failure:
        clickhouse_http.read_rows(ClickHouseConfig("localhost", password="private"), "SELECT 1", {}, 2)

    assert "private" not in str(failure.value)
    assert "wait_end_of_query=1" in connection.request.call_args.args[1]
    connection.close.assert_called_once()
