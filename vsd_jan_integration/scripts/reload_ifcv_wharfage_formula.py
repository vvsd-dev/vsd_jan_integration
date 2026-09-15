"""Set Wharfage to By Formula and reload IFCV-2026-00004."""

from __future__ import annotations

import frappe
from frappe.utils import flt

from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
	load_from_import_file,
)

IMPORT_FILE = "N.TAN039/26MSC"
IFCV = "IFCV-2026-00004"


def run():
	frappe.db.set_value("Costing", "wharfage", "allocation_scope", "By Formula", update_modified=False)
	frappe.clear_cache()
	frappe.db.commit()

	data = load_from_import_file(IMPORT_FILE)
	doc = frappe.get_doc("Import File Cost Voucher", IFCV)
	doc.set("vehicles", [])
	doc.set("expenses", [])
	doc.set("allocations", [])
	for v in data["vehicles"]:
		doc.append("vehicles", v)
	for e in data["expenses"]:
		doc.append("expenses", e)
	doc._distribute_allocations(keep_manual=False)
	doc.total_expense_amount = sum(flt(r.amount) for r in (doc.expenses or []))
	doc.total_allocated_amount = sum(flt(r.amount) for r in (doc.allocations or []))
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	wharf_exp = next((e for e in doc.expenses if e.costing_head == "wharfage"), None)
	print("wharfage method", wharf_exp.distribution_method if wharf_exp else None, "amt", wharf_exp.amount if wharf_exp else None)

	print("\n=== Wharfage per chassis (expect TRA×0.07) ===")
	for a in doc.allocations:
		if a.costing_head != "wharfage":
			continue
		tra = next(
			(
				x.amount
				for x in doc.allocations
				if x.item == a.item and x.costing_head == "tra_duty"
			),
			0,
		)
		expect = flt(tra) * 0.07
		print(
			a.chassis_no,
			"TRA",
			tra,
			"wharf",
			round(flt(a.amount), 2),
			"expect",
			round(expect, 2),
			"OK" if abs(flt(a.amount) - expect) < 1 else "DIFF",
		)
	return doc.name
