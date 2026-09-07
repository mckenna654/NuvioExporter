"""run.py - Application entrypoint with dynamic port and logging configuration."""

from __future__ import annotations

import os
import sys
import uvicorn

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port_str = os.getenv("PORT", "7088")
    
    try:
        port = int(port_str)
    except ValueError:
        sys.stderr.write(f"Invalid PORT value '{port_str}', defaulting to 7088\n")
        port = 7088

    print(f"🚀 Starting NuvioExporter on http://{host}:{port}")
    sys.stdout.flush()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
        access_log=False,  # Compatibility URLs carry private bearer tokens.
    )
