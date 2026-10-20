# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Selling-side costing: Sales Invoice → Journal Entry for Selling / Both heads.

Excel (1 BL COST.xlsx NEW COST FILE):
  CITY LEVY TAX = Expected Selling Price × 0.3%
  VAT (cost)    = (Expected Selling Price × 18%) × 20%
"""

from __future__ import annotations

import hashlib

import frappe
from frappe.utils import flt, today

from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
	get_heads,
	is_selling_side,
	recalculate_car_costing,
)
from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
	is_vehicle_item,
	pick_import_file,
)


def get_selling_costing_heads():
	"""Active Selling / Both heads with GL accounts (any entry_mode)."""
	heads = get_heads(costing_side="Selling")
	out = []
	for h in heads:
		if not h.account or not h.payable_account:
			continue
		if not is_selling_side(h.get("costing_side")):
			continue
		out.append(h)
	return out


def _si_unit_price_company_currency(si, item_row):
	"""Selling price for one vehicle line in company (base) currency."""
	base_rate = flt(item_row.get("base_rate"))
	if base_rate:
		return base_rate
	rate = flt(item_row.get("rate"))
	conv = flt(si.conversion_rate) or 1.0
	return rate * conv


def _selling_je_cheque(si_name, item_code):
	return f"SELL|{si_name}|{item_code}"[:140]


def _selling_je_name(si_name, item_code):
	digest = hashlib.md5(f"SELL|{si_name}|{item_code}".encode()).hexdigest()[:12].upper()
	base = f"SCJV-{digest}"
	if not frappe.db.exists("Journal Entry", base):
		return base
	for n in range(1, 50):
		candidate = f"{base}-{n}"
		if not frappe.db.exists("Journal Entry", candidate):
			return candidate
	return f"{base}-{frappe.generate_hash(length=4)}"


def _ensure_car_costing_with_esp(item_code, expected_selling_price, import_file=None):
	"""Ensure draft Car Costing, set ESP, recalculate Selling formula lines."""
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		ensure_draft_car_costing,
	)
	from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
		get_heads,
		load_template_lines,
		merge_existing_lines,
		sort_costing_lines,
	)

	cc_name = ensure_draft_car_costing(item_code, import_file=import_file)
	if not cc_name:
		return None

	cc = frappe.get_doc("Car Costing", cc_name)

	# Ensure Selling heads (City Levy / VAT) exist on older Car Costings
	existing_tz = [r.as_dict() for r in (cc.get("tz_costing_lines") or [])]
	existing_jp = [r.as_dict() for r in (cc.get("japan_costing_lines") or [])]
	active = {h.costing_code for h in get_heads()}
	cc.set(
		"tz_costing_lines",
		sort_costing_lines(
			[r for r in merge_existing_lines(load_template_lines("Tanzania"), existing_tz) if r["costing_code"] in active]
		),
	)
	cc.set(
		"japan_costing_lines",
		sort_costing_lines(
			[r for r in merge_existing_lines(load_template_lines("Japan"), existing_jp) if r["costing_code"] in active]
		),
	)

	if flt(expected_selling_price) > 0:
		cc.expected_selling_price = flt(expected_selling_price)
	recalculate_car_costing(cc)
	cc.flags.skip_push_to_item = True
	cc.save(ignore_permissions=True)
	cc.flags.skip_push_to_item = False
	try:
		cc.push_expected_to_item()
	except Exception:
		frappe.log_error(
			title=f"Car Costing push after ESP {cc_name}",
			message=frappe.get_traceback(),
		)
	return cc


def _amounts_from_car_costing(cc, heads):
	"""Map costing_code → projected amount from Car Costing lines."""
	by_code = {}
	for line in list(cc.get("tz_costing_lines") or []) + list(cc.get("japan_costing_lines") or []):
		by_code[line.costing_code] = flt(line.projected_amount)

	rows = []
	for h in heads:
		amt = flt(by_code.get(h.costing_code))
		if amt <= 0 and h.entry_mode == "Fixed":
			amt = flt(h.default_projected_amount)
		if amt <= 0:
			continue
		rows.append((h, amt))
	return rows


def create_selling_journal_entry(si, item_code, amounts, chassis=None, import_file=None, auto_submit=True):
	"""One JE per SI item with all Selling/Both debit lines + payable credits."""
	company = si.company
	if not company or not amounts:
		return None, False

	cheque_no = _selling_je_cheque(si.name, item_code)
	existing = frappe.db.get_value(
		"Journal Entry",
		{"cheque_no": cheque_no, "company": company, "docstatus": ["!=", 2]},
		["name", "docstatus"],
		as_dict=True,
	)
	if existing:
		if auto_submit and existing.docstatus == 0:
			jv = frappe.get_doc("Journal Entry", existing.name)
			jv.flags.ignore_mandatory = True
			jv.submit()
		return existing.name, False

	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	cost_center = (
		frappe.db.get_value("Company", company, "cost_center")
		or frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
	)

	jv = frappe.new_doc("Journal Entry")
	jv.name = _selling_je_name(si.name, item_code)
	jv.voucher_type = "Journal Entry"
	jv.company = company
	jv.posting_date = si.posting_date or today()
	jv.cheque_no = cheque_no
	jv.cheque_date = jv.posting_date
	jv.user_remark = f"SELLING COSTING | {si.name} | {chassis or item_code} | {item_code}"
	jv.title = f"Selling Costing | {si.name} | {chassis or item_code}"[:140]
	jv.multi_currency = 0

	if hasattr(jv, "import_file") and import_file:
		jv.import_file = import_file
	if frappe.db.has_column("Journal Entry", "custom_item"):
		jv.custom_item = item_code
	if frappe.db.has_column("Journal Entry", "custom_chassis_no") and chassis:
		jv.custom_chassis_no = chassis

	from collections import defaultdict

	payable_totals = defaultdict(float)
	for h, amt in amounts:
		jv.append(
			"accounts",
			{
				"account": h.account,
				"debit_in_account_currency": amt,
				"debit": amt,
				"account_currency": h.currency or comp_currency,
				"exchange_rate": 1.0,
				"cost_center": cost_center,
				"user_remark": f"{h.costing_name or h.costing_code} | SI {si.name}",
			},
		)
		payable_totals[h.payable_account] += amt

	for payable_acc, tot in payable_totals.items():
		jv.append(
			"accounts",
			{
				"account": payable_acc,
				"credit_in_account_currency": tot,
				"credit": tot,
				"account_currency": comp_currency,
				"exchange_rate": 1.0,
				"cost_center": cost_center,
				"user_remark": f"Payable for Selling Costing — {si.name} / {chassis or item_code}",
			},
		)

	jv.total_debit = sum(flt(r.debit) for r in jv.accounts)
	jv.total_credit = sum(flt(r.credit) for r in jv.accounts)
	jv.difference = abs(flt(jv.total_debit) - flt(jv.total_credit))

	jv.flags.ignore_mandatory = True
	jv.flags.ignore_permissions = True
	jv.flags.ignore_links = True

	try:
		jv.insert(ignore_permissions=True, set_name=jv.name)
	except TypeError:
		jv.insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		jv.name = _selling_je_name(si.name, item_code)
		try:
			jv.insert(ignore_permissions=True, set_name=jv.name)
		except TypeError:
			jv.insert(ignore_permissions=True)

	if auto_submit and jv.docstatus == 0:
		jv.flags.ignore_mandatory = True
		jv.submit()

	return jv.name, True


def _write_selling_actuals(item_code, amounts):
	"""Stamp Selling head actuals onto Item costing child tables."""
	if not item_code or not amounts:
		return
	if not frappe.db.has_column("Item", "custom_tz_costing") and not frappe.get_meta("Item").has_field(
		"custom_tz_costing"
	):
		return

	amt_by_code = {h.costing_code: amt for h, amt in amounts}
	item = frappe.get_doc("Item", item_code)
	changed = False
	for table in ("custom_tz_costing", "custom_japan_costing"):
		for row in item.get(table) or []:
			if row.costing_code in amt_by_code:
				row.actual_amount = amt_by_code[row.costing_code]
				changed = True
	if changed:
		from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
			refresh_item_expense_totals,
		)

		refresh_item_expense_totals(item)
		item.flags.ignore_permissions = True
		item.save()


def process_sales_invoice_selling_costing(si):
	"""Create + submit Selling JEs for vehicle lines on a submitted Sales Invoice."""
	if not si or si.docstatus != 1:
		return {"journal_entries": [], "errors": []}

	heads = get_selling_costing_heads()
	if not heads:
		return {"journal_entries": [], "errors": [], "skipped": "no_selling_heads"}

	created = []
	errors = []

	for row in si.get("items") or []:
		item_code = (row.get("item_code") or "").strip()
		if not item_code or not is_vehicle_item(item_code):
			continue

		esp = _si_unit_price_company_currency(si, row)
		if esp <= 0:
			errors.append(f"{item_code}: selling price is zero")
			continue

		try:
			import_file = pick_import_file(item_code)
			cc = _ensure_car_costing_with_esp(item_code, esp, import_file=import_file)
			if not cc:
				errors.append(f"{item_code}: could not create Car Costing")
				continue

			amounts = _amounts_from_car_costing(cc, heads)
			if not amounts:
				continue

			chassis = (frappe.db.get_value("Item", item_code, "custom_chassis_no") or "").strip()
			je_name, was_new = create_selling_journal_entry(
				si,
				item_code,
				amounts,
				chassis=chassis,
				import_file=import_file,
				auto_submit=True,
			)
			if je_name:
				created.append({"item": item_code, "journal_entry": je_name, "created": was_new})
				if was_new:
					_write_selling_actuals(item_code, amounts)
		except Exception:
			frappe.log_error(
				title=f"Selling Costing SI {si.name} / {item_code}",
				message=frappe.get_traceback(),
			)
			errors.append(f"{item_code}: see Error Log")

	return {"journal_entries": created, "errors": errors}


def cancel_selling_journal_entries_for_si(si):
	"""Cancel submitted Selling JEs linked to this Sales Invoice (cheque_no prefix)."""
	if not si:
		return
	prefix = f"SELL|{si.name}|"
	names = frappe.get_all(
		"Journal Entry",
		filters={
			"company": si.company,
			"cheque_no": ["like", f"{prefix}%"],
			"docstatus": 1,
		},
		pluck="name",
	)
	for name in names:
		try:
			frappe.get_doc("Journal Entry", name).cancel()
		except Exception:
			frappe.log_error(
				title=f"Cancel Selling JE {name} for SI {si.name}",
				message=frappe.get_traceback(),
			)
