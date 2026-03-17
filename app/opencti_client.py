import asyncio
import logging
import os
from typing import Any, Dict, List

import httpx

logging.basicConfig(level=logging.ERROR, format="%(asctime)s %(levelname)s:%(message)s")

OPENCTI_URL_INTEGRATION = os.getenv("OPENCTI_URL_INTEGRATION", "http://opencti:8080")
OPENCTI_TOKEN = os.getenv("OPENCTI_TOKEN", "")

VERIFY = os.getenv("OPENCTI_TLS_VERIFY", "false").lower() == "true"
TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS", "60"))
RETRIES = int(os.getenv("HTTP_RETRIES", "2"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "40"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "10"))

GRAPHQL_URL = f"{OPENCTI_URL_INTEGRATION}/graphql"

HEADERS = {"Authorization": f"Bearer {OPENCTI_TOKEN}", "Content-Type": "application/json", }

HTTP_CLIENT = httpx.AsyncClient(verify=VERIFY, timeout=TIMEOUT, headers=HEADERS,
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=10), )

sem = asyncio.Semaphore(CONCURRENCY)

_GQL_observable = """
query Search($search: String!, $first: Int) {
  stixCyberObservables(search: $search, first: $first) {
    edges {
      node {
        id
        observable_value
        ... on StixCyberObservable {
          observable_value
          x_opencti_description
          x_opencti_score
        }
        created_at
        updated_at
        objectLabel {
          value
        }
        createdBy {
          ... on Identity {
            name
          }
        }
        reports(first: 10) {
          edges {
            node {
              id
            }
          }
        }
      }
    }
  }
}
"""

_GQL_indicator = """
query Search($filterGroup: FilterGroup!, $first: Int) {
  indicators(filters: $filterGroup, first: $first) {
    edges {
      node {
        id
        name
        description
        pattern
        created_at
        updated_at
        valid_from
        valid_until
        x_opencti_score
        objectLabel {
          value
        }
        createdBy {
          ... on Identity {
            name
          }
        }
        reports(first: 10) {
          edges {
            node {
              id
             }
          }
        }
      }
    }
  }
}
"""


def chunked(seq: List[str], size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


async def _post_graphql(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = await HTTP_CLIENT.post(GRAPHQL_URL, json=payload)
    r.raise_for_status()

    data = r.json()

    if data.get("errors"):
        raise RuntimeError(data["errors"])

    return data["data"]


def _indicator_payload(search: List[str]) -> Dict[str, Any]:
    return {
        "query": _GQL_indicator,
        "variables": {
        "filterGroup": {
            "mode": "or",
            "filters": [
                {
                    "key": "name",
                    "values": search,
                    "operator": "contains"
                }
            ],
            "filterGroups": []
        },
        "first": max(50, len(search) * 2)
        }
    }


def _observable_payload(search: str) -> Dict[str, Any]:
    return {
        "query": _GQL_observable,
        "variables": {
            "search": search,
            "first": 10
        }
    }


async def _safe_fetch(batch: List[str], type_: str) -> Any:
    async with sem:
        if type_ == "i":
            payload = _indicator_payload(batch)
            return await _post_graphql(payload)
        else:
            tasks = [_post_graphql(_observable_payload(value)) for value in batch]
            results = await asyncio.gather(*tasks)

            result_map = {}

            for value, r in zip(batch, results):
                edges = r.get("stixCyberObservables", {}).get("edges", [])
                nodes = [e.get("node") for e in edges if e.get("node")]
                if nodes:
                    result_map[value] = nodes

            return result_map


async def query_opencti(search: List[str], type_: str) -> Dict[str, List[Dict[str, Any]]]:
    if not search:
        return {}

    for attempt in range(max(1, RETRIES)):
        try:
            tasks = [_safe_fetch(batch, type_) for batch in chunked(search, BATCH_SIZE)]
            results = await asyncio.gather(*tasks)

            result_map: Dict[str, List[Dict[str, Any]]] = {}

            for r in results:

                if type_ == "i":
                    edges = r.get("indicators", {}).get("edges", [])

                    for e in edges:
                        node = e.get("node") or {}
                        name = node.get("name")

                        if name:
                            result_map.setdefault(name, []).append(node)

                else:
                    for key, nodes in r.items():
                        result_map.setdefault(key, []).extend(nodes)

            return result_map

        except Exception:
            logging.exception("OpenCTI request failed (attempt %s)", attempt + 1)
            await asyncio.sleep(0.5 * (attempt + 1))

    raise RuntimeError("OpenCTI request failed")
