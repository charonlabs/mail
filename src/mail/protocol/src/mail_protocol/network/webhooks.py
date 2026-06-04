# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Addison Kline

from datetime import datetime

from pydantic import BaseModel

from mail_protocol.core.webhooks import MAILMessageInWebhook, MAILWebhookEventType


class WebhookDeliveredPostRequest(BaseModel):
    """
    JSON request body for the MAIL webhook `delivered`.
    The MAIL server POSTs this request to another server;
    this does NOT correspond to an endpoint exposed by the MAIL server itself.
    """

    event: MAILWebhookEventType
    event_id: str
    delivered_at: datetime
    message: MAILMessageInWebhook
