# Copyright (c) 2026, VV Systems Developer LTD and contributors
"""Create + submit two test Sales Invoices for Jan Sale Report verification."""

from __future__ import annotations


def run():
	import frappe
	from frappe.utils import flt, today

	frappe.connect()
	frappe.set_user("Administrator")

	company = (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or "Jan International Limited"
	)
	customer = "Ibrahim" if frappe.db.exists("Customer", "Ibrahim") else frappe.db.get_value(
		"Customer", {"disabled": 0}, "name"
	)
	warehouse = "Sample Warehouse - JIL"
	if not frappe.db.exists("Warehouse", warehouse):
		warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0}, "name")

	cars = [
		{
			"item": "TOYOTA NOAH - ZRR70-0198971",
			"rate": 22_000_000,
			"label": "IFCV",
		},
		{
			"item": "NISSAN JUKE - YF15-019010",
			"rate": 18_500_000,
			"label": "NON_IFCV",
		},
	]

	results = []
	for c in cars:
		item = c["item"]
		# Skip if already has submitted SI
		existing = frappe.db.sql(
			"""
			SELECT si.name
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
			WHERE si.docstatus = 1 AND sii.item_code = %s
			LIMIT 1
			""",
			item,
			pluck=True,
		)
		if existing:
			results.append({"label": c["label"], "item": item, "si": existing[0], "skipped": True})
			print("SKIP_EXISTING", c["label"], item, existing[0])
			continue

		qty = frappe.db.get_value(
			"Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"
		)
		print("STOCK", item, warehouse, qty)

		si = frappe.new_doc("Sales Invoice")
		si.company = company
		si.customer = customer
		si.posting_date = today()
		si.set_posting_time = 1
		si.update_stock = 1
		si.append(
			"items",
			{
				"item_code": item,
				"qty": 1,
				"rate": c["rate"],
				"warehouse": warehouse,
			},
		)
		si.flags.ignore_permissions = True
		try:
			si.insert()
			si.submit()
			frappe.db.commit()
			results.append(
				{
					"label": c["label"],
					"item": item,
					"si": si.name,
					"rate": c["rate"],
					"docstatus": si.docstatus,
					"skipped": False,
				}
			)
			print("SUBMITTED", c["label"], si.name, item, c["rate"])
		except Exception as e:
			frappe.db.rollback()
			print("FAIL", c["label"], item, e)
			# Retry without stock update
			try:
				si2 = frappe.new_doc("Sales Invoice")
				si2.company = company
				si2.customer = customer
				si2.posting_date = today()
				si2.set_posting_time = 1
				si2.update_stock = 0
				si2.append(
					"items",
					{
						"item_code": item,
						"qty": 1,
						"rate": c["rate"],
						"warehouse": warehouse,
					},
				)
				si2.flags.ignore_permissions = True
				si2.insert()
				si2.submit()
				frappe.db.commit()
				results.append(
					{
						"label": c["label"],
						"item": item,
						"si": si2.name,
						"rate": c["rate"],
						"docstatus": si2.docstatus,
						"skipped": False,
						"no_stock": True,
					}
				)
				print("SUBMITTED_NO_STOCK", c["label"], si2.name, item)
			except Exception as e2:
				frappe.db.rollback()
				results.append({"label": c["label"], "item": item, "error": str(e2)})
				print("FAIL2", c["label"], e2)

	# Verify selling JEs
	for r in results:
		if not r.get("si"):
			continue
		jes = frappe.db.sql(
			"""
			SELECT name, cheque_no, custom_item, docstatus
			FROM `tabJournal Entry`
			WHERE docstatus = 1 AND cheque_no LIKE %s
			""",
			(f"SELL|{r['si']}|%",),
			as_dict=True,
		)
		r["selling_jes"] = jes
		print("JES", r["si"], jes)

	return results
