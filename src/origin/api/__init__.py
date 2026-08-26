"""HTTP layer: the four endpoints of section 12 plus the SSE stream.

The package deliberately does not import the application here. Running the
server is `uvicorn origin.api.app:app`, and tests reach for `origin.api.app`.
An empty package saves an import cycle between `app`, `routes` and `jobs`.
"""
