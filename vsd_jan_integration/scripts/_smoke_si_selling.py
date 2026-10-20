# Copyright (c) 2026, VV Systems Developer LTD and contributors
# SI selling costing smoke — creates+cancels a throwaway SI when safe.


def run(item_code=None, selling_price=None, dry_run=0):
	"""Smoke: one JE per vehicle item with all Selling heads + custom_item.

	Passes dry_run=1 to only validate heads/amounts without posting.
	"""
	import frappe
	from frappe.utils import flt, today

	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		is_vehicle_item,
		pick_import_file,
	)
	from vsd_jan_integration.vsd_jan_international_customization.utils.selling_costing import (
		_amounts_from_car_costing,
		_ensure_car_costing_with_esp,
		_selling_je_cheque,
		cancel_selling_journal_entries_for_si,
		create_selling_journal_entry,
		get_selling_costing_heads,
		process_sales_invoice_selling_costing,
	)

	dry_run = int(dry_run or 0)
	heads = get_selling_costing_heads()
	if not heads:
		return {"ok": False, "error": "no_selling_heads"}

	# Pick a vehicle with Car Costing if not provided
	if not item_code:
		item_code = frappe.db.sql(
			"""
			SELECT cc.item
			FROM `tabCar Costing` cc
			INNER JOIN `tabItem` i ON i.name = cc.item
			WHERE IFNULL(cc.item, '') != ''
				AND IFNULL(i.disabled, 0) = 0
			ORDER BY cc.modified DESC
			LIMIT 1
			""",
			pluck=True,
		)
		item_code = item_code[0] if item_code else None
	if not item_code or not is_vehicle_item(item_code):
		return {"ok": False, "error": "no_vehicle_item"}

	esp = flt(selling_price) or 12_500_000
	import_file = pick_import_file(item_code)
	cc = _ensure_car_costing_with_esp(item_code, esp, import_file=import_file)
	amounts = _amounts_from_car_costing(cc, heads)
	print("ITEM", item_code, "ESP", esp, "AMOUNTS", [(h.costing_code, a) for h, a in amounts])

	# Ensure only Selling/Both — never Purchase-only Fixed heads
	for h, _a in amounts:
		side = h.get("costing_side") or "Purchase"
		assert side in ("Selling", "Both"), f"Purchase head in selling JE: {h.costing_code}"

	if dry_run:
		print("DRY_RUN_OK")
		return {
			"ok": True,
			"dry_run": True,
			"item": item_code,
			"amounts": {h.costing_code: a for h, a in amounts},
		}

	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")
	warehouse = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0}, "name"
	)
	if not customer:
		return {"ok": False, "error": "no_customer"}

	# Prefer reusing process_sales_invoice_selling_costing via a minimal SI doc object
	# Build a real draft SI, submit via process only (skip stock if needed)
	si = frappe.new_doc("Sales Invoice")
	si.company = company
	si.customer = customer
	si.posting_date = today()
	si.set_posting_time = 1
	si.update_stock = 0
	si.append(
		"items",
		{
			"item_code": item_code,
			"qty": 1,
			"rate": esp,
			"base_rate": esp,
			"warehouse": warehouse,
		},
	)
	# Don't insert/submit full SI (stock/tax/permissions) — call JE builder directly
	si.name = f"SMOKE-SI-{frappe.generate_hash(length=8)}"
	si.docstatus = 1

	chassis = (frappe.db.get_value("Item", item_code, "custom_chassis_no") or "").strip()
	je_name, was_new = create_selling_journal_entry(
		si,
		item_code,
		amounts,
		chassis=chassis,
		import_file=import_file,
		auto_submit=True,
	)
	je = frappe.get_doc("Journal Entry", je_name) if je_name else None
	print(
		"JE",
		je_name,
		"new",
		was_new,
		"docstatus",
		je.docstatus if je else None,
		"custom_item",
		getattr(je, "custom_item", None) if je else None,
		"cheque",
		je.cheque_no if je else None,
		"debits",
		[(r.account, r.debit) for r in je.accounts if flt(r.debit)] if je else None,
	)

	ok = bool(
		je
		and je.docstatus == 1
		and getattr(je, "custom_item", None) == item_code
		and je.cheque_no == _selling_je_cheque(si.name, item_code)
		and len([r for r in je.accounts if flt(r.debit)]) == len(amounts)
	)

	# Cleanup: cancel + delete smoke JE
	if je and je.docstatus == 1:
		je.cancel()
	if je_name and frappe.db.exists("Journal Entry", je_name):
		frappe.delete_doc("Journal Entry", je_name, force=1, ignore_permissions=True)
	frappe.db.commit()

	print("OK" if ok else "FAIL")
	return {
		"ok": ok,
		"item": item_code,
		"journal_entry": je_name,
		"was_new": was_new,
		"amounts": {h.costing_code: a for h, a in amounts},
	}
