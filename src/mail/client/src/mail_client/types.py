# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from httpx import HTTPStatusError, Request, Response


class MAILRequestError(HTTPStatusError):
    """
    An error raised when a request to a MAIL server fails.
    """
    def __init__(
        self,
        status_code: int,
        detail: str,
        request: Request,
        response: Response,
    ) -> None:
        super().__init__(request=request, response=response, message=detail)


class MAILResponseError(Exception):
    """
    An error raised when a response from a MAIL server is invalid.
    """
    def __init__(
        self,
        detail: str,
    ) -> None:
        super().__init__(detail)