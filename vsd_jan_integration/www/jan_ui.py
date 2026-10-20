import frappe
from frappe.utils import get_system_timezone

no_cache = 1


def get_context():
	csrf_token = frappe.sessions.get_csrf_token()
	context = frappe._dict()
	context.boot = get_boot()
	context.boot.csrf_token = csrf_token
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw("This method is only meant for developer mode")
	return get_boot()


@frappe.whitelist()
def get_session_user():
	if frappe.session.user == "Guest":
		return None
	return {
		"name": frappe.session.user,
		"full_name": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user,
		"user_image": frappe.db.get_value("User", frappe.session.user, "user_image") or "",
		"roles": frappe.get_roles(frappe.session.user),
	}


def get_boot():
	socketio_port = frappe.conf.get("socketio_port") or 9000
	data = frappe._dict(
		{
			"frappe_version": frappe.__version__,
			"site_name": frappe.local.site,
			"sitename": frappe.local.site,
			"socketio_port": socketio_port,
			"dev_server": 1 if getattr(frappe.local, "dev_server", 0) else 0,
			"read_only_mode": frappe.flags.read_only,
			"system_timezone": get_system_timezone(),
		}
	)
	if frappe.session.user != "Guest":
		data.user = {
			"name": frappe.session.user,
			"full_name": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user,
			"user_image": frappe.db.get_value("User", frappe.session.user, "user_image") or "",
			"roles": frappe.get_roles(frappe.session.user),
		}
	else:
		data.user = None
	return data
