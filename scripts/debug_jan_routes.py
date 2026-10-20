from werkzeug.routing import Map, Rule
from frappe.website.path_resolver import get_website_rules, resolve_path, PathResolver
import frappe

rules = [
	Rule(r["from_route"], endpoint=r["to_route"], defaults=r.get("defaults"))
	for r in get_website_rules()
]
route_map = Map(rules)
environ = {
	"REQUEST_METHOD": "GET",
	"PATH_INFO": "/jan_ui/dashboard",
	"SERVER_NAME": "dev15-jan.vvsdtz.com",
	"SERVER_PORT": "443",
	"wsgi.url_scheme": "https",
	"SCRIPT_NAME": "",
}
# Attach a fake request so evaluate_dynamic_routes works
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

builder = EnvironBuilder(path="/jan_ui/dashboard", base_url="https://dev15-jan.vvsdtz.com/")
env = builder.get_environ()
frappe.local.request = Request(env)

print("resolve_path", resolve_path("jan_ui/dashboard"))
print("PathResolver valid", PathResolver("jan_ui/dashboard").is_valid_path())
print("PathResolver resolve", PathResolver("jan_ui/dashboard").resolve())

urls = route_map.bind_to_environ(env)
print("werkzeug match", urls.match("/jan_ui/dashboard"))
