"""The FastAPI application."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import Engine

from radar import __version__
from radar.api.live import LiveHub
from radar.api.routes import router
from radar.api.schemas import LiveBar, LiveNews
from radar.db.session import make_engine
from radar.universe import Universe, get_universe


def create_app(engine: Engine | None = None, universe: Universe | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        hub: LiveHub = app.state.hub
        hub.start(app.state.engine, asyncio.get_running_loop())
        try:
            yield
        finally:
            hub.stop()

    app = FastAPI(
        title="RADAR",
        version=__version__,
        description=(
            "Market outlook analytics for Bitcoin, gold, and US stocks. Analytics only:"
            " this API never places trades. All timestamps are UTC."
        ),
        lifespan=lifespan,
    )
    app.state.engine = engine or make_engine()
    app.state.universe = universe or get_universe()
    app.state.hub = LiveHub()
    app.include_router(router)

    # Publish the WebSocket message shapes in the OpenAPI schema, so the frontend's
    # generated types cover them too.
    original = app.openapi

    def openapi_with_live_events() -> dict[str, object]:
        schema = original()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in (LiveBar, LiveNews):
            components.setdefault(
                model.__name__, model.model_json_schema(ref_template="#/components/schemas/{model}")
            )
        return schema

    app.openapi = openapi_with_live_events  # type: ignore[method-assign]
    return app
