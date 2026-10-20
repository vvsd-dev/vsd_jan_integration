#!/usr/bin/env python3
"""Smoke: multi-IFCV oneshot exclusion + BL-wide share on N.TAN039 (or any Import File).

Usage (from bench):
  bench --site dev15-jan.vvsdtz.com execute \\
    vsd_jan_integration.scripts.smoke_multi_ifcv_bl.run --kwargs "{'import_file': 'N.TAN039'}"

Does not submit or mutate submitted docs. Creates a temporary draft simulation in memory
when possible; prints consumed keys + BL share for a 1-car subset.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


def run(import_file: str = "N.TAN039/26MSC"):
	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		get_consumed_oneshot_expense_keys,
		get_posted_expenses,
		get_vehicles_for_import_file,
		is_bl_wide_distribution,
		is_oneshot_distribution,
		load_from_import_file,
	)

	if not frappe.db.exists("Import File", import_file):
		# try by import_file_number or partial name
		alt = frappe.db.get_value("Import File", {"import_file_number": import_file}, "name")
		if not alt:
			rows = frappe.get_all(
				"Import File",
				filters={"name": ["like", f"%{import_file}%"]},
				pluck="name",
				limit=1,
			)
			alt = rows[0] if rows else None
		if alt:
			import_file = alt
		else:
			# fall back to most recently modified Import File
			rows = frappe.get_all(
				"Import File", order_by="modified desc", pluck="name", limit=1
			)
			if rows:
				print(f"Import File '{import_file}' missing; falling back to {rows[0]}")
				import_file = rows[0]
			else:
				print(f"Import File not found: {import_file}")
				return {"ok": False, "error": "missing import file"}

	vehicles = get_vehicles_for_import_file(import_file)
	print(f"Import File {import_file}: {len(vehicles)} vehicles")
	for v in vehicles[:10]:
		print(f"  - {v.name} chassis={v.get('custom_chassis_no')} m3={v.get('custom_m3')}")

	consumed = get_consumed_oneshot_expense_keys(import_file)
	print(f"Consumed oneshot keys from submitted IFCVs: {len(consumed)}")
	for k in list(consumed)[:15]:
		print(f"  consumed {k}")

	all_exp = get_posted_expenses(import_file, apply_oneshot_filter=False)
	filtered = get_posted_expenses(import_file, apply_oneshot_filter=True)
	print(f"Posted expenses raw={len(all_exp)} after oneshot filter={len(filtered)}")

	oneshot_raw = [
		e for e in all_exp if is_oneshot_distribution(e.get("distribution_method"), e.get("allocation_scope"))
	]
	oneshot_kept = [
		e for e in filtered if is_oneshot_distribution(e.get("distribution_method"), e.get("allocation_scope"))
	]
	bl_kept = [
		e for e in filtered if is_bl_wide_distribution(e.get("distribution_method"), e.get("allocation_scope"))
	]
	print(f"  oneshot raw={len(oneshot_raw)} kept={len(oneshot_kept)}  bl/formula kept={len(bl_kept)}")

	data = load_from_import_file(import_file)
	print(f"load_from_import_file → vehicles={len(data['vehicles'])} expenses={len(data['expenses'])}")

	# Simulate partial IFCV (first car only) BL Equal share
	if not vehicles:
		return {"ok": False, "error": "no vehicles"}

	bl_n = len(vehicles)
	doc = frappe.new_doc("Import File Cost Voucher")
	doc.import_file = import_file
	doc.posting_date = frappe.utils.today()
	first = data["vehicles"][0]
	doc.append("vehicles", first)
	for e in data["expenses"]:
		if is_bl_wide_distribution(e.get("distribution_method"), e.get("allocation_scope")):
			doc.append("expenses", e)
			break
	if not doc.expenses:
		print("No BL-wide expense to simulate; skipping distribute check")
		return {
			"ok": True,
			"import_file": import_file,
			"vehicles": bl_n,
			"consumed_oneshot": len(consumed),
			"expenses_filtered": len(filtered),
		}

	doc._sync_expense_distribution_from_costing()
	doc._distribute_allocations(keep_manual=False)
	exp = doc.expenses[0]
	allocs = [a for a in (doc.allocations or []) if a.source_row == exp.idx]
	expected = flt(exp.amount) / bl_n if bl_n else 0
	got = flt(allocs[0].amount) if allocs else 0
	print(
		f"Partial IFCV (1/{bl_n}) expense={exp.costing_head} full={exp.amount} "
		f"alloc_rows={len(allocs)} share={got} expected≈{expected}"
	)
	ok = bool(allocs) and abs(got - expected) < 1.0
	print("PASS" if ok else "FAIL — BL share mismatch")
	# Do not insert/save
	return {
		"ok": ok,
		"import_file": import_file,
		"vehicles": bl_n,
		"consumed_oneshot": len(consumed),
		"expenses_filtered": len(filtered),
		"partial_share": got,
		"expected_share": expected,
	}
