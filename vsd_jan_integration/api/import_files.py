import frappe
from frappe import _
from frappe.utils import cint


def _import_file_fields():
	"""Only request columns that exist on this site's Import File."""
	meta = frappe.get_meta("Import File")
	wanted = [
		"name",
		"bl_number",
		"supplier_invoice_no",
		"supplier_name",
		"import_file_number",
		"invoice_currency",
		"invoice_amount",
		"docstatus",
		"modified",
	]
	return [f for f in wanted if f == "name" or f == "docstatus" or f == "modified" or meta.has_field(f)]


@frappe.whitelist()
def list_import_files(search=None, limit=50, start=0):
	frappe.has_permission("Import File", "read", throw=True)
	limit = min(cint(limit) or 50, 200)
	start = cint(start) or 0
	search = (search or "").strip()

	fields = _import_file_fields()
	values = {}
	where = ["1=1"]
	if search:
		where.append(
			"""(
				name LIKE %(q)s
				OR IFNULL(bl_number, '') LIKE %(q)s
				OR IFNULL(supplier_invoice_no, '') LIKE %(q)s
				OR IFNULL(supplier_name, '') LIKE %(q)s
				OR IFNULL(import_file_number, '') LIKE %(q)s
			)"""
		)
		values["q"] = f"%{search}%"

	where_sql = " AND ".join(where)
	field_sql = ", ".join(f"`{f}`" for f in fields)
	total = frappe.db.sql(f"SELECT COUNT(*) FROM `tabImport File` WHERE {where_sql}", values)[0][0]
	rows = frappe.db.sql(
		f"""
		SELECT {field_sql}
		FROM `tabImport File`
		WHERE {where_sql}
		ORDER BY modified DESC
		LIMIT {limit} OFFSET {start}
		""",
		values,
		as_dict=True,
	)
	# Normalize for frontend (supplier alias)
	for row in rows:
		row["supplier"] = row.get("supplier_name") or row.get("supplier")
	return {"import_files": rows, "total": cint(total)}


@frappe.whitelist()
def get_import_file(name):
	frappe.has_permission("Import File", "read", throw=True)
	if not name or not frappe.db.exists("Import File", name):
		frappe.throw(_("Import File {0} not found").format(name), frappe.DoesNotExistError)

	doc = frappe.get_doc("Import File", name)
	out = {
		"name": doc.name,
		"bl_number": doc.get("bl_number"),
		"supplier_invoice_no": doc.get("supplier_invoice_no"),
		"supplier_name": doc.get("supplier_name"),
		"supplier": doc.get("supplier_name"),
		"import_file_number": doc.get("import_file_number"),
		"invoice_currency": doc.get("invoice_currency"),
		"invoice_amount": doc.get("invoice_amount"),
		"docstatus": doc.docstatus,
		"company": None,
	}

	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		get_vehicles_for_import_file,
	)

	vehicles = get_vehicles_for_import_file(name)
	out["vehicle_count"] = len(vehicles)
	out["vehicles"] = [
		{
			"name": v.get("name"),
			"chassis_no": v.get("custom_chassis_no"),
			"maker": v.get("custom_maker"),
			"stock_id": v.get("custom_new_stock_id"),
		}
		for v in vehicles[:50]
	]

	ifcvs = frappe.get_all(
		"Import File Cost Voucher",
		filters={"import_file": name, "docstatus": ["<", 2]},
		fields=["name", "posting_date", "docstatus", "total_expense_amount", "total_allocated_amount"],
		order_by="modified desc",
	)
	out["ifcvs"] = ifcvs
	return out
