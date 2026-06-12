# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Charon Labs (contribution PR)

import os

# The drift test imports mail_server.server, which reads MAIL_HOST and
# (via routers.auth) MAIL_JWT_EXPIRE_MINUTES at import time. The values
# do not affect the generated schema — mirror the placeholders used by
# scripts/generate_openapi.py.
os.environ.setdefault("MAIL_HOST", "localhost")
os.environ.setdefault("MAIL_JWT_EXPIRE_MINUTES", "15")
