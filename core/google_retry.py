"""Bounded retries at the Google request boundary, never replaying mutations."""
import json
import time
import socket
import ssl
import httplib2


def transient(exc):
    status = getattr(getattr(exc, 'resp', None), 'status', None)
    if status in (429, 500, 502, 503, 504):
        return True
    if status == 403:
        try:
            errors = json.loads(exc.content)['error'].get('errors', [])
            return any(e.get('reason') in ('rateLimitExceeded', 'userRateLimitExceeded')
                       for e in errors)
        except (AttributeError, ValueError, KeyError, TypeError):
            return False
    return isinstance(exc, (TimeoutError, ConnectionError, socket.gaierror,
                            ssl.SSLError, httplib2.ServerNotFoundError))


def retry_read(operation, sleep=None):
    for attempt in range(3):
        try:
            return operation()
        except Exception as exc:
            if attempt == 2 or not transient(exc):
                if attempt == 2:
                    # Higher-level read workflows must not multiply this budget.
                    exc.google_read_retries_exhausted = True
                raise
            (sleep or time.sleep)(0.5 * 2 ** attempt)


class safe_service:
    """Wrap resource methods, including failures while constructing requests.

    Writes deliberately use the original request unchanged. Transport-level
    401 refresh remains Google's responsibility, not a replay of a workflow.
    """
    def __init__(self, service):
        self._service = service

    def __getattr__(self, name):
        def resource(*args, **kwargs):
            return _Resource(getattr(self._service, name)(*args, **kwargs))
        return resource


class _Resource:
    def __init__(self, resource):
        self._resource = resource

    def __getattr__(self, name):
        method = getattr(self._resource, name)
        if name not in ('get', 'list', 'get_media', 'export'):
            return method

        def request(*args, **kwargs):
            class ReadRequest:
                def execute(self):
                    return retry_read(lambda: method(*args, **kwargs).execute())
            return ReadRequest()
        return request
