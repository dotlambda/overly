# TODO
# 1. Add a way to nicely override automatic request getting for
#    partials, headers only etc.
# 2. Add a way to config headers per steps set, keep-alive etc.


import h11

import time
import json
from functools import partial
from urllib.parse import urlparse, unquote_plus
from http.cookies import SimpleCookie

from .http_utils import (
    get_content_type,
    extract_query,
    extract_form_urlencoded,
    extract_cookies,
    cookies_to_key_value,
    cookiest_to_output,
    create_content_len_header,
)
from .errors import EndSteps

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --------------
# Response Endings
# --------------


def finish(client_handler):
    client_handler.http_send(h11.EndOfMessage())
    client_handler.http_send(h11.ConnectionClosed())


def just_close(client_handler):
    client_handler.http_send(h11.ConnectionClosed())


def just_end(client_handler):
    client_handler.http_send(h11.EndOfMessage())


def just_kill():
    raise EndSteps


# ---------------------
# 200 <= method <= 299
# ---------------------


def send_request_as_json(client_handler, headers=None):
    response_data = _prepare_request_as_json(client_handler)
    logger.info("Request as json: {}".format(response_data))

    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
        ("content-type", "application/json"),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=200, http_version=b"1.1", reason=b"OK", headers=response_headers
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


def _prepare_request_as_json(client_handler) -> dict:
    _, _, path, _, query, _ = urlparse(client_handler.request.target)

    content_type = get_content_type(client_handler.request.headers)

    data = {}
    data["http_version"] = client_handler.request.http_version.decode()
    data["method"] = client_handler.request.method.decode()
    data["target"] = client_handler.request.target.decode()
    data["path"] = path.decode()

    if query:
        data["params"] = extract_query(unquote_plus(query.decode()))

    if content_type == b"application/x-www-form-urlencoded":
        data.update(
            {
                "form": extract_form_urlencoded(
                    unquote_plus(client_handler.request_body.decode())
                )
            }
        )

    data.update(
        {
            "headers": [
                [header.decode(), value.decode()]
                for header, value in client_handler.request.headers
            ]
        }
    )

    data["body"] = client_handler.request_body.decode()
    logger.info(client_handler.request_body.decode())

    return json.dumps(data).encode()


def accept_cookies_and_respond(client_handler, headers=None, data=None):
    cookies = extract_cookies(client_handler.request.headers)
    cookies_for_body = cookies_to_key_value(cookies)
    cookies_for_header = cookiest_to_output(cookies)

    response_data = prepare_cookies_response(cookies_for_body)

    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
        ("content-type", "application/json"),
        ("cookie", cookies_for_header),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=200, http_version=b"1.1", reason=b"OK", headers=response_headers
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


def prepare_cookies_response(cookies: SimpleCookie) -> bytes:
    cookies = {k: v for k, v in [cookie.split('=') for cookie in cookies]}
    data = {'cookies': cookies}
    return json.dumps(data).encode()


def send_200(client_handler, headers=None, data=None, delay_body=None):
    response_data = data or b"200"

    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=200, http_version=b"1.1", reason=b"OK", headers=response_headers
        )
    )

    if delay_body is not None:
        logger.info("Delaying body by {} seconds.".format(delay_body))
        time.sleep(delay_body)

    client_handler.http_send(h11.Data(data=response_data))


def send_204(client_handler, headers=None, data=None):
    response_data = data or b""
    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=204,
            http_version=b"1.1",
            reason=b"NO CONTENT",
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


# ---------------------
# 300 <= method <= 399
# ---------------------


def send_3xx(status_code, reason_phrase, client_handler, headers=None, data=None):
    response_data = data or str(status_code).encode()

    response_headers = [
        ("location", client_handler.http_test_url),
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=status_code,
            http_version=b"1.1",
            reason=reason_phrase.encode(),
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


send_301 = partial(send_3xx, status_code=301, reason_phrase="MOVED PERMANENTLY")
send_302 = partial(send_3xx, status_code=302, reason_phrase="FOUND")
send_303 = partial(send_3xx, 303, "SEE OTHER")


def send_304(client_handler, headers=None, data=None):
    response_data = data or b"304"

    response_headers = [
        ("location", client_handler.http_test_url),
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=304,
            http_version=b"1.1",
            reason=b"NOT MODIFIED",
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


# ---------------------
# 400 <= method <= 499
# ---------------------


def send_400(client_handler, headers=None, data=None):
    response_data = data or b"400"
    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=400,
            http_version=b"1.1",
            reason=b"BAD REQUEST",
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


def send_403(client_handler, headers=None, data=None):
    response_data = data or b"403"
    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=403,
            http_version=b"1.1",
            reason=b"FORBIDDEN",
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


def send_404(client_handler, headers=None, data=None):
    response_data = data or b"404"
    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=404,
            http_version=b"1.1",
            reason=b"NOT FOUND",
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


def send_405(client_handler, headers=None, data=None):
    response_data = data or b"405"
    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=405,
            http_version=b"1.1",
            reason=b"METHOD NOT ALLOWED",
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


def method_check(client_handler, correct_method):
    """
    If the check fails, sends a 405
    """
    if not client_handler.request.method == correct_method.encode():
        send_405(client_handler)
        raise EndSteps


# ---------------------
# 500 <= method <= 599
# ---------------------


def send_500(client_handler, headers=None, data=None):
    response_data = data or b"I'm pretending to be broken >:D"
    response_headers = [
        ("connection", "close"),
        create_content_len_header(response_data),
    ]

    if headers is not None:
        response_headers = _add_external_headers(response_headers, headers)

    client_handler.http_send(
        h11.Response(
            status_code=500,
            http_version=b"1.1",
            reason=b"INTERNAL SERVER ERROR",
            headers=response_headers,
        )
    )

    client_handler.http_send(h11.Data(data=response_data))


# -------------------------
# implementation modifiers
# -------------------------


def receive_request(client_handler):
    """
    This func is duplicated as a method in ClientHandler.
    It is required for deciding which method and path to act on
    when multiple steps are defined.
    """
    request = client_handler.http_next_event()
    while True:
        event = client_handler.http_next_event()
        if isinstance(event, h11.EndOfMessage):
            break
        elif isinstance(event, h11.Data):
            client_handler.request_body += event.data

    client_handler.request = request


def delay(t=0):
    def delay_(t, *_):
        time.sleep(t)

    return partial(delay_, t)


# ---------------
# Internal utils
# ---------------


def _add_external_headers(internal_headers, external_headers):
    new_headers = []

    e_keys = [e_key for e_key, _ in external_headers]

    for i_key, i_value in internal_headers:
        if i_key not in e_keys:
            new_headers.append((i_key, i_value))

    new_headers.extend(external_headers)

    return new_headers
