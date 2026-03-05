from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi_server.front_apis import app as front_app
from fastapi_server.server_dashscope import create_dashscope_router


app = FastAPI(
    title="Combined Front + DashScope APIs",
    description=(
        "Single-process app exposing front_apis control endpoints and "
        "DashScope-compatible chat endpoints."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Keep existing /v1/... admin APIs unchanged.
app.include_router(front_app.router)

# Add DashScope endpoints at their existing URLs. We intentionally skip
# DashScope's root/health routes to avoid clashing with front_apis.
app.include_router(create_dashscope_router(include_meta_routes=False))

