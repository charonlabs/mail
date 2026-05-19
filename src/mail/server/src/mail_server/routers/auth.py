# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token")
async def create_auth_token():
    return {"message": "Hello from POST /auth/token!"}


@router.get("/whoami")
async def get_token_info():
    return {"message": "Hello from GET /auth/whoami!"}
