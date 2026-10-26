"""Quick local backend import check."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app

print(f"CampusGuard AI backend loaded: {app.title} v{app.version}")
def list_routes(routes, prefix=""):
    for route in routes:
        if hasattr(route, "routes"):
            list_routes(route.routes, prefix + getattr(route, "path", ""))
        else:
            methods = ",".join(sorted(getattr(route, "methods", []) or []))
            path = prefix + getattr(route, "path", "")
            print(f"  {methods:10} {path}")

print("Routes:")
list_routes(app.routes)
