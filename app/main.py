"""NuvioExporter: local collection-layout conversion."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from fastapi.exceptions import RequestValidationError

from app.fusion import convert_to_fusion
from app.bridge import BridgeError, BridgePlan, BridgeService, PAGE_SIZE, ProfileStore
from app.upstream import UpstreamError
from app.remux import RemuxService, RemuxError
from urllib.parse import parse_qsl

ROOT = Path(__file__).parent
MAX_REQUEST_BYTES = 10 * 1024 * 1024
VERSION = '3.0.1'
APP_NAME = 'NuvioExporter'
app = FastAPI(title=APP_NAME, version=VERSION,
              description='Convert Nuvio collections for Fusion or import their catalog setup into Remux.',
              docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')
app.state.bridge = BridgeService(ProfileStore(os.getenv('NUVIO2FUSION_DATA_DIR', str(ROOT.parent / 'data'))))
app.state.remux = RemuxService(app.state.bridge.store)


class RequestBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        if scope['method'] == 'POST':
            origin = headers.get(b'origin')
            if origin and urlsplit(origin.decode()).netloc != headers.get(b'host', b'').decode():
                return await JSONResponse({'detail': 'Cross-origin requests are blocked.'}, 403)(scope, receive, send)
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > MAX_REQUEST_BYTES:
                    return await JSONResponse({'detail': 'Request exceeds 10 MiB.'}, 413)(scope, receive, send)
                if not message.get('more_body'):
                    break
            consumed = False

            async def bounded_receive():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()
            await self.app(scope, bounded_receive, send)
        else:
            await self.app(scope, receive, send)


app.add_middleware(RequestBoundary)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Input values and mapping keys can both contain private install URLs.
    return JSONResponse({'detail': 'Invalid request fields. Supply export_data and an optional addon_urls object mapping addon IDs to URL strings.'}, status_code=422)


@app.middleware('http')
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    if request.url.path.startswith('/bridge/'):
        response.headers['Access-Control-Allow-Origin'] = '*'
    return response


class FusionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    export_data: Any
    addon_urls: dict[str, str] = Field(default_factory=dict)
    bridge_url: str | None = None
    omit_empty_folders: bool = False


class RemuxPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    export_data: Any
    addon_urls: dict[str, str] = Field(default_factory=dict)
    bridge_url: str | None = None
    server_url: str
    api_key: str = Field(repr=False, min_length=1, max_length=4096)
    setup_name: str = Field(default='My Nuvio setup', min_length=1, max_length=100)


class RemuxImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_token: str
    api_key: str = Field(repr=False, min_length=1, max_length=4096)


@app.post('/api/remux/preview')
def remux_preview(request: RemuxPreviewRequest, http_request: Request):
    try:
        return http_request.app.state.remux.preview(**request.model_dump())
    except RemuxError as exc:
        raise HTTPException(400, str(exc)) from None
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise HTTPException(400, 'Invalid Nuvio setup or Remux response. Check the source JSON, addon URLs and server version.') from None


@app.post('/api/remux/import')
def remux_import(request: RemuxImportRequest, http_request: Request):
    try:
        return http_request.app.state.remux.apply(request.preview_token, request.api_key)
    except RemuxError as exc:
        raise HTTPException(409, str(exc)) from None
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise HTTPException(502, 'Unexpected Remux response. Some changes may have applied; preview again before retrying.') from None


@app.get('/')
async def index():
    return FileResponse(ROOT / 'templates' / 'index.html')


@app.get('/api/health')
async def health():
    return {'status': 'ok', 'app': APP_NAME, 'version': VERSION}


@app.get('/api/bridge/settings')
def bridge_settings():
    return {'publicUrl': os.getenv('NUVIO2FUSION_PUBLIC_URL', ''),
            'privateUpstreamsAllowed': os.getenv('NUVIO2FUSION_ALLOW_PRIVATE_UPSTREAM') == '1'}


@app.exception_handler(BridgeError)
async def bridge_error(request, exc):
    return JSONResponse({'detail': str(exc)}, status_code=503)


@app.exception_handler(UpstreamError)
async def upstream_error(request, exc):
    return JSONResponse({'error': str(exc)}, status_code=502)


@app.get('/bridge/{token}/manifest.json')
def bridge_manifest(token: str, request: Request):
    try:
        return request.app.state.bridge.manifest(token)
    except KeyError:
        raise HTTPException(404, 'Unknown compatibility profile. Keep the appdata used to generate this export.') from None


@app.get('/bridge/{token}/catalog/{typ}/{cid}.json')
@app.get('/bridge/{token}/catalog/{typ}/{cid}/{path_extra}.json')
def bridge_catalog(token: str, typ: str, cid: str, request: Request, path_extra: str = ''):
    try:
        path_pairs = parse_qsl(path_extra, keep_blank_values=True, strict_parsing=True) if path_extra else []
        query_pairs = list(request.query_params.multi_items())
        if (any(k != 'skip' for k, _ in path_pairs) or
                any(k not in {'skip', 'limit', 'extra'} for k, _ in query_pairs) or
                len(path_pairs) != len(dict(path_pairs)) or
                len(query_pairs) != len(dict(query_pairs))):
            raise ValueError
        values = dict(path_pairs)
        query = dict(query_pairs)
        if 'skip' in query:
            if 'skip' in values:
                raise ValueError
            values['skip'] = query['skip']
        # Fusion sends its generic catalog client options on the first request
        # as ?limit=N&extra={}. This fixed profile accepts only an empty extra
        # object or a numeric skip within it; arbitrary upstream options remain
        # blocked so the route cannot become an open proxy.
        if query.get('extra'):
            embedded = json.loads(query['extra'])
            if not isinstance(embedded, dict) or any(k != 'skip' for k in embedded):
                raise ValueError
            if 'skip' in embedded:
                if 'skip' in values or type(embedded['skip']) not in {int, str}:
                    raise ValueError
                values['skip'] = str(embedded['skip'])
        offset = values.get('skip', '0')
        limit = query.get('limit', str(PAGE_SIZE))
        if not offset.isdigit() or len(offset) > 6 or not limit.isdigit() or len(limit) > 3:
            raise ValueError
        return request.app.state.bridge.catalog(token, typ, cid, int(offset), int(limit))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(400, 'Only a bounded page size and non-negative skip offset are supported by this fixed catalog.') from None
    except KeyError:
        raise HTTPException(404, 'Unknown compatibility profile or catalog.') from None


@app.get('/api/presets/{name}')
async def preset(name: str):
    files = {'nuvio': 'nuvio_collections.json', 'fusion': 'fusion_example.json'}
    if name not in files:
        raise HTTPException(404, 'Unknown example.')
    return {'rawData': json.loads((ROOT / 'presets' / files[name]).read_text())}


@app.post('/api/fusion/convert')
def fusion_convert(request: FusionRequest, http_request: Request):
    try:
        plan = BridgePlan(http_request.app.state.bridge.store, request.bridge_url) if request.bridge_url else None
        return convert_to_fusion(request.export_data, request.addon_urls, plan, request.omit_empty_folders)
    except (ValueError, TypeError, AttributeError, KeyError, RecursionError):
        raise HTTPException(400, 'Invalid export or addon mapping. Use Nuvio collections JSON or Fusion widget v1 JSON, and full HTTP(S) manifest URLs for mappings. Check array/object fields.') from None
