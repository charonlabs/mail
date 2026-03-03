# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from .core import (
    MAILAddress,
    MAILInstance,
    MAILMessage,
    MAILServerSentEvent,
    MAILTask,
)
from .interswarm import (
    MAILInterswarmAttachment,
    MAILInterswarmMessage,
    MAILInterswarmTask,
    MAILRemoteSwarm,
)

__all__ = [
    "MAILAddress",
    "MAILMessage",
    "MAILTask",
    "MAILInstance",
    "MAILServerSentEvent",
    "MAILInterswarmAttachment",
    "MAILInterswarmMessage",
    "MAILInterswarmTask",
    "MAILRemoteSwarm",
]