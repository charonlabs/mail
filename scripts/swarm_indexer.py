# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

"""Build an index of reachable MAIL swarms."""

import argparse
import asyncio
import datetime
import json
from typing import Any

import aiohttp


async def _is_valid_swarm_response(response_json: dict[str, Any]) -> bool:
    REQUIRED_FIELDS = {
        "swarms": list,
    }

    SWARM_REQUIRED_FIELDS = {
        "swarm_name": str,
        "base_url": str,
        "version": str,
        "last_seen": str,
        "is_active": bool,
        "swarm_description": str,
        "keywords": list,
    }

    for field, field_type in REQUIRED_FIELDS.items():
        if field not in response_json:
            return False
        if not isinstance(response_json[field], field_type):
            return False

    for swarm in response_json.get("swarms", []):
        for field, field_type in SWARM_REQUIRED_FIELDS.items():  # type: ignore
            if field not in swarm:
                print(f"ERROR: {field} not in swarm")
                return False
            if not isinstance(swarm[field], field_type):
                print(f"ERROR: {field} is not a {field_type.__name__}")
                return False

    return True


async def _get_swarm_info(url: str) -> list[dict[str, Any]]:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{url}/swarms") as response:
                if response.status != 200:
                    print(f"ERROR getting swarm from {url}: {response.status}")
                    return []
                json_response = await response.json()
                if not await _is_valid_swarm_response(json_response):
                    print(f"ERROR getting swarm from {url}: not a valid MAIL swarm")
                    return []
                print(f"found {len(json_response.get('swarms', []))} swarms from {url}")
                return json_response.get("swarms", [])
        except Exception as e:
            print(f"ERROR getting swarm from {url}: {e}")
            return []


async def _clean_swarm_results(
    results: list[list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    combined_list = [result for sublist in results for result in sublist if result]

    # remove duplicates
    # each swarm is unique by its name and base_url
    unique_swarms: dict[str, dict[str, Any]] = {}
    for swarm in combined_list:
        swarm_key = f"{swarm['swarm_name']}@{swarm['base_url']}"
        if swarm_key not in unique_swarms:
            unique_swarms[swarm_key] = swarm
        else:
            if swarm["last_seen"] > unique_swarms[swarm_key]["last_seen"]:
                unique_swarms[swarm_key] = swarm

    print(f"found {len(unique_swarms)} unique swarms")

    return unique_swarms


async def _crawl_swarms(urls: list[str]) -> dict[str, dict[str, Any]]:
    tasks = []
    for url in urls:
        tasks.append(_get_swarm_info(url))
    task_results = await asyncio.gather(*tasks)

    return await _clean_swarm_results(task_results)


async def _write_outfile(swarms: dict[str, dict[str, Any]], output_file: str):
    try:
        with open(output_file, "w") as f:
            json.dump(swarms, f, indent=4)
            print(f"wrote {len(swarms)} swarms to {output_file}")
    except Exception as e:
        print(f"ERROR writing to {output_file}: {e}")


async def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("urls", nargs="+", help="URLs of MAIL swarms to index")
    parser.add_argument("--output", help="File to save the index to")

    args = parser.parse_args()

    swarms = await _crawl_swarms(args.urls)

    print(json.dumps(swarms, indent=4))

    if args.output:
        await _write_outfile(swarms, args.output)


if __name__ == "__main__":
    asyncio.run(main())
