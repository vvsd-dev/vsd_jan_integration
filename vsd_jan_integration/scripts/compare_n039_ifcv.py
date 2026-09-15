"""Compare IFCV-2026-00004 allocations vs 1 BL COST.xlsx for N.TAN039/26MSC."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import flt

IFCV = "IFCV-2026-00004"
USD_TZS = 2700.0

EXCEL = {
	"ZRR70-0198971": {
		"m3": 14.733,
		"tra_duty": 9600000,
		"wharfage": 672000,
		"tpa": 141176,
		"icd_usd": 191.529,
		"shipping_usd": 1384.902,
		"yen": 217000,
		"japan_cost_usd": 261,
	},
	"NSP140-9011378": {
		"m3": 11.396,
		"tra_duty": 8600000,
		"wharfage": 602000,
		"tpa": 141176,
		"icd_usd": 148.148,
		"shipping_usd": 1071.224,
		"yen": 118000,
		"japan_cost_usd": 261,
	},
	"RT1-1006295": {
		"m3": 12.508,
		"tra_duty": 9423484.8,
		"wharfage": 659643.936,
		"tpa": 141176,
		"icd_usd": 162.604,
		"shipping_usd": 1175.752,
		"yen": 172000,
		"japan_cost_usd": 261,
	},
	"GRS180-0026901": {
		"m3": 12.664,
		"tra_duty": 10000000,
		"wharfage": 700000,
		"tpa": 141176,
		"icd_usd": 164.632,
		"shipping_usd": 1190.416,
		"yen": 174000,
		"japan_cost_usd": 261,
	},
	"ANH20-8050726": {
		"m3": 16.991,
		"tra_duty": 11600000,
		"wharfage": 812000,
		"tpa": 141176,
		"icd_usd": 220.883,
		"shipping_usd": 1597.154,
		"yen": 202000,
		"japan_cost_usd": 261,
	},
	"ANH15-0044728": {
		"m3": 17.165,
		"tra_duty": 10700000,
		"wharfage": 749000,
		"tpa": 141176,
		"icd_usd": 223.145,
		"shipping_usd": 1613.51,
		"yen": 234000,
		"japan_cost_usd": 261,
	},
	"TRN215-0021658": {
		"m3": 16.502,
		"tra_duty": 21500000,
		"wharfage": 1505000,
		"tpa": 141176,
		"icd_usd": 214.526,
		"shipping_usd": 1551.188,
		"yen": 1257000,
		"japan_cost_usd": 261,
	},
}


def run():
	doc = frappe.get_doc("Import File Cost Voucher", IFCV)
	item_ch = {}
	for v in doc.vehicles:
		ch = (v.chassis_no or "").strip() or frappe.db.get_value("Item", v.item, "custom_chassis_no")
		item_ch[v.item] = ch

	print("IFCV", doc.name, "docstatus", doc.docstatus, "veh", len(doc.vehicles), "exp", len(doc.expenses), "alloc", len(doc.allocations))

	# expense meta
	print("\n=== EXPENSE ROWS (sample fields) ===")
	meta_fields = [df.fieldname for df in frappe.get_meta("Import File Cost Voucher Expense").fields]
	print("expense fields:", [f for f in meta_fields if f in ("costing_head", "account", "amount", "currency", "basis", "allocation_basis", "journal_entry", "linked_item", "item")])

	exp_by = defaultdict(lambda: {"amt": 0.0, "cur": "", "basis": "", "n": 0})
	for e in doc.expenses:
		key = (e.costing_head or e.account or "?")
		exp_by[key]["amt"] += flt(e.amount)
		exp_by[key]["cur"] = e.currency or ""
		basis = getattr(e, "basis", None) or getattr(e, "allocation_basis", None) or ""
		exp_by[key]["basis"] = basis
		exp_by[key]["n"] += 1

	print("\n=== EXPENSES rolled up ===")
	for k, v in sorted(exp_by.items(), key=lambda x: -x[1]["amt"]):
		print(f"{k:35} {v['cur']:4} {v['amt']:>18,.2f}  n={v['n']} basis={v['basis']}")

	alloc = defaultdict(lambda: defaultdict(float))
	for a in doc.allocations:
		ch = (a.chassis_no or "").strip() or item_ch.get(a.item, "") or (a.item or "?")
		head = a.costing_head or a.account or "?"
		alloc[ch][head] += flt(a.amount)

	print("\n=== alloc chassis keys ===", sorted(alloc.keys()))
	print("=== all heads ===", sorted({h for d in alloc.values() for h in d}))

	print("\n=== PER-CAR Excel vs IFCV ===")
	mismatches = []
	for ch, x in EXCEL.items():
		v = next((vv for vv in doc.vehicles if item_ch.get(vv.item) == ch), None)
		row = alloc.get(ch, {})
		print(f"\n-- {ch} m3_excel={x['m3']} m3_ifcv={flt(v.m3) if v else None} pp_excel={x['yen']} pp_ifcv={flt(v.purchase_price) if v else None}")

		checks = [
			("tra_duty", x["tra_duty"], False),
			("tpa", x["tpa"], False),
			("wharfage", x["wharfage"], False),
			("icd", x["icd_usd"] * USD_TZS, True),  # posted as TZS
			("shipping_line", x["shipping_usd"] * USD_TZS, True),
		]
		for head, expected, is_usd in checks:
			got = row.get(head, 0.0)
			if not got:
				for hk, hv in row.items():
					if head.replace("_", "") in (hk or "").lower().replace("_", "").replace(" ", ""):
						got = hv
						head = hk
						break
			diff = got - expected
			ok = abs(diff) < 1.0  # 1 TZS tolerance
			flag = "OK" if ok else "DIFF"
			extra = ""
			if is_usd:
				extra = f" (excel_usd={expected/USD_TZS:.4f})"
			print(f"  {flag:4} {head:20} excel={expected:>14,.2f} ifcv={got:>14,.2f} diff={diff:>12,.2f}{extra}")
			if not ok:
				mismatches.append((ch, head, expected, got, diff))

		# show other heads on this car
		others = {h: a for h, a in row.items() if h not in ("tra_duty", "tpa", "wharfage", "icd", "shipping_line")}
		if others:
			print("  other heads:")
			for h, a in sorted(others.items()):
				print(f"         {h:30} {a:>14,.2f}")

	print(f"\n=== MISMATCHES ({len(mismatches)}) ===")
	for m in mismatches:
		print(m)

	# JE status for this IF
	jes = frappe.db.sql(
		"""
		SELECT name, cheque_no, docstatus, total_debit, user_remark
		FROM `tabJournal Entry`
		WHERE import_file=%s OR cheque_no LIKE %s OR user_remark LIKE %s
		ORDER BY name
		""",
		(IFCV.replace("IFCV-", ""), "%%N.TAN039%%", "%%N.TAN039%%"),
		as_dict=True,
	)
	# better query
	jes = frappe.db.sql(
		"""
		SELECT name, cheque_no, docstatus, total_debit, LEFT(IFNULL(user_remark,''),80) AS remark
		FROM `tabJournal Entry`
		WHERE IFNULL(import_file,'')=%s
		   OR cheque_no LIKE '%%N.TAN039%%'
		   OR cheque_no LIKE 'ACTUAL|%%'
		   OR name LIKE 'FCJV-%%'
		   OR name LIKE 'MKTJV-6C902EA45F05'
		ORDER BY creation
		""",
		("N.TAN039/26MSC",),
		as_dict=True,
	)
	print("\n=== JEs linked / related ===")
	for j in jes:
		# filter to our cars / BL
		print(j.name, "ds", j.docstatus, "debit", j.total_debit, "cheque", j.cheque_no, "|", j.remark)

	return {"ifcv": doc.name, "mismatches": len(mismatches)}
