"""Bounded JSONEachRow transport for the APP-07 ClickHouse adapters."""
import json
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from urllib.parse import urlencode


def read_rows(config, query, parameters, row_limit, byte_limit=32 * 1024 * 1024):
    params = urlencode({"readonly": 1, **{"param_" + name: value for name, value in parameters.items()}})
    connect = HTTPSConnection if config.secure else HTTPConnection
    connection = connect(config.host, config.port, timeout=config.connect_timeout)
    rows = []
    try:
        connection.connect()
        connection.sock.settimeout(config.query_timeout)
        connection.request("POST", f"/?{params}", body=query.encode("utf8"),
                           headers={"X-ClickHouse-User": config.username,
                                    "X-ClickHouse-Key": config.password})
        with connection.getresponse() as response:
            if response.status != 200:
                raise RuntimeError(f"ClickHouse Gold returned HTTP {response.status}")
            while line := response.readline(byte_limit + 1):
                byte_limit -= len(line)
                if byte_limit < 0 or len(rows) >= row_limit:
                    raise ValueError("ClickHouse result exceeds APP-02 read limit")
                rows.append(json.loads(line))
    except (HTTPException, OSError) as exc:
        raise RuntimeError(f"Could not read ClickHouse Gold ({type(exc).__name__})") from None
    finally:
        connection.close()
    return rows
