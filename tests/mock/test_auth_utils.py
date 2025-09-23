# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

from mail.utils.auth import generate_agent_id, generate_user_id


def test_generate_user_id():
	"""
	Ensure `generate_user_id` works as expected.
	"""
	token_info = {"role": "user", "id": "abc"}
	assert generate_user_id(token_info) == "user_abc"


def test_generate_agent_id():
	"""
	Ensure `generate_agent_id` works as expected.
	"""
	token_info = {"role": "agent", "id": "xyz"}
	assert generate_agent_id(token_info) == "swarm_xyz"
