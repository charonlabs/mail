# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025-26 Addison Kline

from pydantic import BaseModel


#
# Authentication endpoints
#
class PostAuthTokenRequest(BaseModel):
    """
    Submit valid credentials to obtain a JWT for subsequent use.
    """

    pass
