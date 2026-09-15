"""Recreate Fixed JEs (no clearing) for N.TAN039 and reload IFCV."""

from __future__ import annotations

import frappe
from frappe.utils import flt

from vsd_jan_integration.scripts.setup_n039_bl_cost import CC, IMPORT_FILE, _submit_je
from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
	load_from_import_file,
)
from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
	ensure_fixed_costing_for_items,
	get_fixed_costing_heads,
)


def run():
	heads = get_fixed_costing_heads()
	print("fixed heads (By Vehicle actual only):", [h.costing_code for h in heads])
	assert "clearing_container" not in [h.costing_code for h in heads]

	codes = frappe.db.sql(
		"""
		SELECT DISTINCT pii.item_code
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name=pii.parent
		WHERE pi.import_file=%s AND pi.docstatus < 2
		""",
		IMPORT_FILE,
		pluck=True,
	)
	res = ensure_fixed_costing_for_items(codes, auto_submit_jv=False, import_file=IMPORT_FILE)
	print("created", len(res["journal_entries"]), "errors", res["errors"])
	for je in res["journal_entries"]:
		frappe.db.sql(
			"UPDATE `tabJournal Entry Account` SET cost_center=%s WHERE parent=%s AND IFNULL(cost_center,'')=''",
			(CC, je),
		)
		has_clear = frappe.db.sql(
			"SELECT 1 FROM `tabJournal Entry Account` WHERE parent=%s AND account LIKE 'Clearing%%' LIMIT 1",
			je,
		)
		ds = frappe.db.get_value("Journal Entry", je, "docstatus")
		if ds == 0:
			_submit_je(je)
		print(" FIXED", je, "clearing?" , bool(has_clear), "ds", frappe.db.get_value("Journal Entry", je, "docstatus"))

	# Reload IFCV
	existing = frappe.db.get_value(
		"Import File Cost Voucher", {"import_file": IMPORT_FILE, "docstatus": 0}, "name"
	)
	data = load_from_import_file(IMPORT_FILE)
	doc = frappe.get_doc("Import File Cost Voucher", existing)
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

	null_ch = sum(1 for a in doc.allocations if not a.chassis_no)
	by_method = {}
	for e in doc.expenses:
		key = (e.costing_head or e.expense_account, e.distribution_method)
		by_method[key] = by_method.get(key, 0) + 1
	print("IFCV", doc.name, "exp", len(doc.expenses), "alloc", len(doc.allocations), "null_chassis", null_ch)
	for k, n in sorted(by_method.items(), key=lambda x: str(x[0])):
		print(" ", k, "n=", n)
	# Noah view sample
	for a in doc.allocations:
		if a.chassis_no == "ZRR70-0198971":
			print(" Noah", a.costing_head, a.amount, a.chassis_no)
	return doc.name
