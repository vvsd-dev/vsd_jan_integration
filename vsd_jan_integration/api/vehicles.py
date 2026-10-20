import json

import frappe
from frappe import _
from frappe.utils import cint, flt


def _resolve_item_name(item):
	"""Accept Item name or chassis no (common in vehicle URLs / search)."""
	item = (item or "").strip()
	if not item:
		return None
	if frappe.db.exists("Item", item):
		return item
	by_chassis = frappe.db.get_value("Item", {"custom_chassis_no": item}, "name")
	if by_chassis:
		return by_chassis
	# Unique suffix match: "… - CHASSIS" naming used by MKT imports
	rows = frappe.get_all(
		"Item",
		filters={"name": ["like", f"% - {item}"]},
		fields=["name"],
		limit_page_length=2,
	)
	if len(rows) == 1:
		return rows[0]["name"]
	return None


VEHICLE_IDENTITY_FIELDS = [
	"name",
	"item_code",
	"item_name",
	"stock_uom",
	"disabled",
	"custom_chassis_no",
	"custom_maker",
	"custom_model",
	"custom_model_code",
	"custom_new_stock_id",
	"custom_bl",
	"custom_container_no",
	"custom_price",
	"custom_m3",
	"custom_purchase_date",
	"custom_purchase_company",
]

VEHICLE_SPEC_FIELDS = [
	"custom_exhibition_no",
	"custom_engine_code",
	"custom_engine_cc",
	"custom_drive_type",
	"custom_doors",
	"custom_seats",
	"custom_transmission",
	"custom_fuel_type",
	"custom_steering",
	"custom_mileage",
	"custom_manufactured_year",
	"custom_gradeclass",
	"custom_color",
	"custom_interior_color",
	"custom_auction_company",
	"custom_auction_no",
	"custom_mukechi",
	"custom_bid_by",
	"custom_territory",
	"custom_loaded_docs_status",
	"custom_days_since_purchase",
	"custom_highest_bids_remarks",
]

FEATURE_FIELDS = [
	"custom_power_steering",
	"custom_amfm_radio",
	"custom_ac",
	"custom_rear_spoiler",
	"custom_air_bag",
	"custom_fog_light",
	"custom_power_window",
	"custom_navigation",
	"custom_tv",
	"custom_push_start",
	"custom_abs",
	"custom_power_mirror",
	"custom_spare_tyre",
	"custom_key_start",
	"custom_alloy_wheel",
	"custom_sunroof",
]

COSTING_FIELDS = [
	"custom_exchange_rate",
	"custom_total_expected_expense",
	"custom_total_actual_expense",
	"custom_cost",
	"custom_selling_price",
	"custom_profit_usd",
	"custom_last_car_costing",
]

EDITABLE_FIELDS = set(
	VEHICLE_IDENTITY_FIELDS
	+ VEHICLE_SPEC_FIELDS
	+ FEATURE_FIELDS
	+ ["item_name"]
) - {"name", "item_code", "stock_uom", "disabled"}


def _vehicle_filters(search=None):
	filters = {"disabled": 0}
	or_filters = [
		["custom_chassis_no", "is", "set"],
		["custom_maker", "is", "set"],
	]
	return filters, or_filters, (search or "").strip()


@frappe.whitelist()
def get_dashboard_stats():
	frappe.has_permission("Item", "read", throw=True)
	vehicles = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabItem`
		WHERE IFNULL(disabled, 0) = 0
			AND (IFNULL(custom_chassis_no, '') != '' OR IFNULL(custom_maker, '') != '')
		"""
	)[0][0]
	import_files = frappe.db.count("Import File")
	open_ifcvs = frappe.db.count("Import File Cost Voucher", {"docstatus": 0})
	submitted_ifcvs = frappe.db.count("Import File Cost Voucher", {"docstatus": 1})
	recent = frappe.get_all(
		"Import File",
		fields=["name", "bl_number", "modified"],
		order_by="modified desc",
		limit=8,
	)
	return {
		"vehicles": cint(vehicles),
		"import_files": cint(import_files),
		"open_ifcvs": cint(open_ifcvs),
		"submitted_ifcvs": cint(submitted_ifcvs),
		"recent_import_files": recent,
	}


@frappe.whitelist()
def list_vehicles(search=None, limit=50, start=0):
	frappe.has_permission("Item", "read", throw=True)
	limit = min(cint(limit) or 50, 200)
	start = cint(start) or 0
	search = (search or "").strip()

	conditions = [
		"IFNULL(disabled, 0) = 0",
		"(IFNULL(custom_chassis_no, '') != '' OR IFNULL(custom_maker, '') != '')",
	]
	values = {}
	if search:
		conditions.append(
			"""(
				name LIKE %(q)s OR item_name LIKE %(q)s
				OR custom_chassis_no LIKE %(q)s OR custom_maker LIKE %(q)s
				OR custom_model LIKE %(q)s OR custom_new_stock_id LIKE %(q)s
				OR custom_bl LIKE %(q)s
			)"""
		)
		values["q"] = f"%{search}%"

	where = " AND ".join(conditions)
	total = frappe.db.sql(f"SELECT COUNT(*) FROM `tabItem` WHERE {where}", values)[0][0]
	rows = frappe.db.sql(
		f"""
		SELECT name, item_name, custom_chassis_no, custom_maker, custom_model,
			custom_new_stock_id, custom_bl, custom_price, custom_m3, custom_cost, modified
		FROM `tabItem`
		WHERE {where}
		ORDER BY modified DESC
		LIMIT {limit} OFFSET {start}
		""",
		values,
		as_dict=True,
	)
	return {"vehicles": rows, "total": cint(total)}


@frappe.whitelist()
def get_vehicle(item):
	frappe.has_permission("Item", "read", throw=True)
	resolved = _resolve_item_name(item)
	if not resolved:
		frappe.throw(_("Item {0} not found").format(item), frappe.DoesNotExistError)
	item = resolved

	fields = VEHICLE_IDENTITY_FIELDS + VEHICLE_SPEC_FIELDS + FEATURE_FIELDS + COSTING_FIELDS
	# dedupe while preserving order
	seen = set()
	ordered = []
	for f in fields:
		if f not in seen:
			seen.add(f)
			ordered.append(f)

	doc = frappe.get_doc("Item", item)
	out = {f: doc.get(f) for f in ordered}
	out["custom_tz_costing"] = [
		{
			"costing_code": r.get("costing_code"),
			"costing_head": r.get("costing_head") or r.get("costing"),
			"expected_amount": flt(r.get("expected_amount")),
			"actual_amount": flt(r.get("actual_amount")),
		}
		for r in (doc.get("custom_tz_costing") or [])
	]
	out["custom_japan_costing"] = [
		{
			"costing_code": r.get("costing_code"),
			"costing_head": r.get("costing_head") or r.get("costing"),
			"expected_amount": flt(r.get("expected_amount")),
			"actual_amount": flt(r.get("actual_amount")),
		}
		for r in (doc.get("custom_japan_costing") or [])
	]
	return out


@frappe.whitelist()
def update_vehicle_specs(item, fields=None):
	frappe.has_permission("Item", "write", throw=True)
	resolved = _resolve_item_name(item)
	if not resolved:
		frappe.throw(_("Item {0} not found").format(item), frappe.DoesNotExistError)
	item = resolved

	if isinstance(fields, str):
		fields = json.loads(fields or "{}")
	fields = fields or {}

	doc = frappe.get_doc("Item", item)
	changed = False
	for key, value in fields.items():
		if key not in EDITABLE_FIELDS:
			continue
		if doc.get(key) != value:
			doc.set(key, value)
			changed = True
	if changed:
		doc.save(ignore_permissions=False)
	return get_vehicle(item)
