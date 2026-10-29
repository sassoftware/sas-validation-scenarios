# Copyright © 2026, SAS Institute Inc., Cary, NC, USA.  All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minimal HTTP client for the Viya probes (stdlib only, honours trusted-certs)."""

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import urlencode


@dataclass
class HttpResponse:
    status: int
    body: bytes

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class HttpError(Exception):
    """The request never reached the server (DNS, TLS, connection, timeout)."""


class HttpClient:
    def __init__(self, trusted_certs: Optional[Path] = None, timeout: float = 30.0):
        self._timeout = timeout
        self._context = ssl.create_default_context(
            cafile=str(trusted_certs) if trusted_certs else None
        )

    def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Mapping[str, str]] = None,
        form: Optional[Mapping[str, str]] = None,
    ) -> HttpResponse:
        data = urlencode(form).encode("utf-8") if form is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        if form is not None:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout, context=self._context
            ) as response:
                return HttpResponse(response.status, response.read())
        except urllib.error.HTTPError as error:
            return HttpResponse(error.code, error.read())
        except Exception as error:
            raise HttpError(str(error)) from error
