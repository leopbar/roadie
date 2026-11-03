"""Ponto de entrada ASGI: `uvicorn roadie.main:app`."""

from roadie.api.app import create_app

app = create_app()
