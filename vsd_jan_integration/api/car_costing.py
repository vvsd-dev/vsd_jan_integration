import json
import importlib

import frappe
from frappe import _
from frappe.utils import flt


def _module():
	return importlib.import_module(
		"vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing"
	)


def _serialize(doc):
	data = doc.as_dict()
	# Ensure child tables are plain lists of dicts
	for key in ("tz_costing_lines", "japan_costing_lines"):
		data[key] = [
			{
				"name": r.get("name"),
				"costing_code": r.get("costing_code"),
				"costing_head": r.get("costing_head"),
				"costing_type": r.get("costing_type"),
				"expected_amount": flt(r.get("expected_amount")),
				"actual_amount": flt(r.get("actual_amount")),
				"idx": r.get("idx"),
			}
			for r in (doc.get(key) or [])
		]
	return data


@frappe.whitelist()
def get_or_create(item):
	frappe.has_permission("Car Costing", "write", throw=True)
	item = (item or "").strip()
	resolved = item
	if item and not frappe.db.exists("Item", item):
		resolved = frappe.db.get_value("Item", {"custom_chassis_no": item}, "name")
		if not resolved:
			rows = frappe.get_all(
				"Item",
				filters={"name": ["like", f"% - {item}"]},
				fields=["name"],
				limit_page_length=2,
			)
			resolved = rows[0]["name"] if len(rows) == 1 else None
	if not resolved:
		frappe.throw(_("Item {0} not found").format(item), frappe.DoesNotExistError)
	name = _module().get_or_create_for_item(resolved)
	doc = frappe.get_doc("Car Costing", name)
	return {"name": doc.name, "doc": _serialize(doc)}


@frappe.whitelist()
def get_car_costing(name):
	frappe.has_permission("Car Costing", "read", throw=True)
	doc = frappe.get_doc("Car Costing", name)
	return _serialize(doc)


@frappe.whitelist()
def save_car_costing(doc):
	frappe.has_permission("Car Costing", "write", throw=True)
	if isinstance(doc, str):
		doc = json.loads(doc)
	name = doc.get("name")
	if not name or not frappe.db.exists("Car Costing", name):
		frappe.throw(_("Car Costing {0} not found").format(name))

	cc = frappe.get_doc("Car Costing", name)
	for field in (
		"costing_date",
		"exchange_rate",
		"yen_exchange_rate",
		"m3",
		"yen",
		"expected_selling_price",
		"import_file",
		"chassis_no",
		"maker",
		"model",
	):
		if field in doc:
			cc.set(field, doc.get(field))

	def apply_lines(fieldname, rows):
		existing_by_code = {r.costing_code: r for r in (cc.get(fieldname) or [])}
		for row in rows or []:
			code = row.get("costing_code")
			if not code:
				continue
			target = existing_by_code.get(code)
			if target:
				target.expected_amount = flt(row.get("expected_amount"))
			else:
				cc.append(
					fieldname,
					{
						"costing_code": code,
						"costing_head": row.get("costing_head"),
						"costing_type": row.get("costing_type"),
						"expected_amount": flt(row.get("expected_amount")),
					},
				)

	apply_lines("tz_costing_lines", doc.get("tz_costing_lines"))
	apply_lines("japan_costing_lines", doc.get("japan_costing_lines"))
	cc.save()
	cc.recalculate(save=True)
	return _serialize(frappe.get_doc("Car Costing", name))


@frappe.whitelist()
def fetch_exchange_rates(docname=None, costing_date=None):
	frappe.has_permission("Car Costing", "write", throw=True)
	return _module().fetch_exchange_rates(docname=docname, costing_date=costing_date or None)


@frappe.whitelist()
def recalculate(docname):
	frappe.has_permission("Car Costing", "write", throw=True)
	return _module().recalculate(docname)


@frappe.whitelist()
def load_from_item(docname=None, item=None, import_file=None):
	frappe.has_permission("Car Costing", "write", throw=True)
	return _module().load_from_item(docname=docname, item=item, import_file=import_file)
