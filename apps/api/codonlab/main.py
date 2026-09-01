"""FastAPI application.

Routes are an HTTP surface only — no business logic. See ARCHITECTURE.md §3.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from codonlab import __version__
from codonlab.config import get_settings
from codonlab.routes import design_sets, goals, meta, projects, runs, targets

app = FastAPI(
    title="Codon Lab API",
    version=__version__,
    description="Protein design copilot. Every score returned by this API carries the "
    "model version and run that produced it.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(projects.router)
app.include_router(targets.router)
app.include_router(goals.router)
app.include_router(runs.router)
app.include_router(design_sets.router)
