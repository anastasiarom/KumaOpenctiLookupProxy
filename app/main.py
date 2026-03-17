import base64
import logging
import os
from typing import List, Dict, Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .models import LookupObject, LookupResult, LookupResultError, Category
from .opencti_client import query_opencti
from .utils import normalize_search_value

app = FastAPI(title="OpenCTI-KUMA Lookup Proxy")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(message)s")
logger = logging.getLogger("lookup")


class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        method = request.method
        try:
            resp = await call_next(request)
            logger.info("%s %s -> %s", method, path, resp.status_code)
            return resp
        except Exception as e:
            logger.exception("Error handling %s %s: %s", method, path, e)
            raise


app.add_middleware(LogMiddleware)

OPENCTI_URL = os.getenv("OPENCTI_URL", "https://opencti.org")

BASIC_USER = os.getenv("LOOKUP_BASIC_USER", "user")
BASIC_PASS = os.getenv("LOOKUP_BASIC_PASSWORD", "password")

MAP_FOUND = "detected"
MAP_NOT_FOUND = "not detected"
MAP_ERROR = "error"


def _check_basic_auth(req: Request):
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        raise HTTPException(status_code=401, detail="Missing Basic auth")
    try:
        b64 = auth.split(" ", 1)[1]
        user_pass = base64.b64decode(b64).decode("utf-8")
        user, pwd = user_pass.split(":", 1)
        if not (user == BASIC_USER and pwd == BASIC_PASS):
            raise HTTPException(status_code=403, detail="Invalid credentials")
    except Exception:
        raise HTTPException(status_code=400, detail="Bad Authorization header")


def _build_category_from_indicator(ind: Dict[str, Any]) -> Category:
    labels = [label['value'] for label in ind.get("objectLabel")]
    ctx = {
        "type": "indicator",
        "name": ind.get("name"),
        "opencti": f"{OPENCTI_URL}/dashboard/observations/indicators/{ind.get('id')}",
        "description": ind.get("description") if ind.get("description") else "-",
        "created_at": ind.get("created_at"),
        "updated_at": ind.get("updated_at"),
        "valid_from": ind.get("valid_from"),
        "valid_until": ind.get("valid_until"),
        "score": str(ind.get("x_opencti_score")) if ind.get("x_opencti_score") is not None else None,
        "labels": ",".join(labels) if labels else "-",
        "created_by": ind.get("createdBy", {}).get("name") if ind.get("createdBy") else None,
    }
    reports = [node for node in ind.get("reports")["edges"] if ind.get("reports")["edges"] != []]
    if reports != []:
        for i, node in enumerate(reports, 1):
            ctx[f"report{i}"] = f'{OPENCTI_URL}/dashboard/analyses/reports/{node["node"]["id"]}'

    return Category(category=f'OpenCTI Enrichment {ind.get("pattern").split(":")[0][1:]}',
                    detected_indicator=ind.get("name") or "indicator", context=ctx)


def _build_category_from_observable(obs: Dict[str, Any], search) -> Category:
    labels = [label['value'] for label in obs.get("objectLabel")]

    ctx = {
        "type": "observable",
        "name": obs.get("observable_value"),
        "opencti": f"{OPENCTI_URL}/dashboard/observations/observables/{obs.get('id')}",
        "description": obs.get("description") if obs.get("description") else "-",
        "created_at": obs.get("created_at"),
        "updated_at": obs.get("updated_at"),
        "score": str(obs.get("x_opencti_score")) if obs.get("x_opencti_score") is not None else None,
        "labels": ",".join(labels) if labels else "-",
        "createdBy": obs.get("createdBy", {}).get("name") if obs.get("createdBy") else None,
    }
    reports = [node for node in obs.get("reports")["edges"] if obs.get("reports")["edges"] != []]
    if reports != []:
        for i, node in enumerate(reports, 1):
            ctx[f"report{i}"] = f'{OPENCTI_URL}/dashboard/analyses/reports/{node["node"]["id"]}'

    return Category(category="OpenCTI Enrichment StixObservables", detected_indicator=search, context=ctx)


@app.get("/health")
async def health():
    return {"status": "ok"}


def _error_response(e: Exception) -> JSONResponse:
    return JSONResponse([LookupResultError(status=MAP_ERROR, reason=str(e)).model_dump()])


async def _parse_request(request: Request) -> List[LookupObject]:
    try:
        payload = await request.json()
        if not isinstance(payload, list):
            raise ValueError
        return [LookupObject(**i) for i in payload]
    except Exception:
        raise HTTPException(status_code=400, detail="Body must be JSON array of {object}")


async def _get_observable_map(
    src: List[str],
    indicator_map: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, List[Dict[str, Any]]]:

    missing_keys = [k for k in src if k not in indicator_map]

    if not missing_keys:
        return {}

    return await query_opencti(missing_keys, "o")


def _build_results(src: List[str], indicator_map: Dict[str, List[Dict[str, Any]]],
        observable_map: Dict[str, List[Dict[str, Any]]], ) -> List[LookupResult]:
    results: List[LookupResult] = []

    for key in src:

        categories: List[Category] = []

        indicator_nodes = []
        for map_key, nodes in indicator_map.items():
            if map_key == key or map_key in key or key in map_key:
                indicator_nodes.extend(nodes)

        for node in indicator_nodes:
            categories.append(_build_category_from_indicator(node))

        if not categories:
            observable_nodes = []
            for map_key, nodes in observable_map.items():
                if map_key == key or map_key in key or key in map_key:
                    observable_nodes.extend(nodes)

            for node in observable_nodes:
                categories.append(_build_category_from_observable(node, key))

        result_type = MAP_FOUND if categories else MAP_NOT_FOUND
        logger.info("%s -> %s", key, result_type)

        results.append(LookupResult(object=key, result=result_type, categories=categories or None))

    return results


@app.post("/api/1.1/lookup")
async def lookup(request: Request):
    _check_basic_auth(request)

    items = await _parse_request(request)

    search, src = normalize_search_value(items)

    try:
        indicator_map = await query_opencti(search, "i")
        missing_keys = [k for k in src if k not in indicator_map]
        observable_map = await query_opencti(missing_keys, "o") if missing_keys else {}
    except Exception as e:
        return _error_response(e)

    results = _build_results(src, indicator_map, observable_map)

    return JSONResponse([r.model_dump() for r in results])
