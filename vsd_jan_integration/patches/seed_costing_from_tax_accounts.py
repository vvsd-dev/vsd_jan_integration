# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Seed Costing from Tax Expense Accounts + named Payables for ALL Costings.

Excel / Car Costing sense:
- Tanzania Expected → TZS
- Japan Expected → USD (Excel sheet), even when the GL account is JPY
- IFCV still reads JE/PI amounts in account currency; Actuals are converted to Costing.currency

Also creates missing expense accounts and named Payable GLs for every active Costing.
"""

from __future__ import annotations

import re

import frappe
from frappe.utils import flt


# Prefer updating these existing Costing codes when tax_name / account matches
ACCOUNT_ALIASES = {
	"JPN Expense JPY - JIL": "japan_cost",
	"Inspection JPY - JIL": "inspection",
	"Forwarding JPY - JIL": "forwarding",
}
NAME_ALIASES = {
	"jpn expense": "japan_cost",
	"inspection": "inspection",
	"forwarding": "forwarding",
}

# Excel Car Costing Japan lines are USD (not account currency)
EXCEL_JAPAN_USD_CODES = {
	"japan_cost",
	"inspection",
	"icd",
	"shipping_line",
	"forwarding",
	"thc",
	"freight",
	"vanning",
	"transportation",
	"freight_other",
	"cont_other_value",
	"inv_other_charges",
	"repair_cost",
	"car_expense",
}

# Canonical Company → Tax Expense Accounts (+ GL).
# Japan rows match MKT EXPENSE_FIELDS labels; TZS rows cover Costing heads
# that are not created from the tax table alone (TRA, Wharfage, Fixed locals, …).
# Tuple: (tax_name, currency, preferred_account_leaf_without_abbr)
DEFAULT_TAX_EXPENSE_ACCOUNTS = [
	# --- Japan / MKT Statement charges (JPY) ---
	("THC", "JPY", "THC JPY"),
	("Forwarding", "JPY", "Forwarding JPY"),
	("Freight", "JPY", "Freight JPY"),
	("Inspection", "JPY", "Inspection JPY"),
	("JPN Expense", "JPY", "JPN Expense JPY"),
	("Repair Cost", "JPY", "Repair Cost JPY"),
	("Car Expense", "JPY", "Car Expense JPY"),
	("Vanning", "JPY", "Vanning JPY"),
	("Transportation", "JPY", "Transportation JPY"),
	("Freight & Other", "JPY", "Freight & Other JPY"),
	("Cont. Other Value", "JPY", "Cont. Other Value JPY"),
	("Inv Other Charges", "JPY", "Inv Other Charges JPY"),
	# --- Tanzania / other Costing expense GLs (company currency) ---
	("TRA Duty", "TZS", "TRA Duty"),
	("Wharfage", "TZS", "Wharfage"),
	("TPA", "TZS", "TPA"),
	("ICD", "TZS", "ICD"),
	("Shipping Line", "TZS", "Shipping Line"),
	("Clearing Container", "TZS", "Clearing Container"),
	("Ex-Bond", "TZS", "Ex-Bond"),
	("Car Service", "TZS", "Car Service"),
	("Bond Insurance", "TZS", "Bond Insurance"),
	("Driver Port to Yard", "TZS", "Driver Port to Yard"),
	("Fuel Port to Yard", "TZS", "Fuel Port to Yard"),
	("Repairing Charges Local", "TZS", "Repairing Charges Local"),
	("City Levy Tax", "TZS", "City Levy Tax"),
	("VAT Costing", "TZS", "VAT Costing"),
]


def _slug(label: str) -> str:
	s = re.sub(r"[^a-zA-Z0-9]+", "_", (label or "").strip().lower()).strip("_")
	return s[:140] or "tax_costing"


def _company() -> str | None:
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		companies = frappe.get_all("Company", pluck="name")
		company = companies[0] if companies else None
	return company


def _ensure_other_payable_group(company: str, currency: str | None = None) -> str | None:
	"""Ensure Liability group 'Other Payable' (or 'Other Payable JPY') under Current Liabilities.

	Blank account_type — leaf payables under it also blank so JE lines need no Supplier party.
	Group currency must match leaf currency (ERPNext rule).
	"""
	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	currency = (currency or comp_currency).strip() or comp_currency

	if currency == comp_currency:
		account_name_only = "Other Payable"
	else:
		account_name_only = f"Other Payable {currency}"

	group_name = f"{account_name_only} - {abbr}" if abbr else account_name_only
	existing = frappe.db.get_value("Account", {"name": group_name, "company": company}, "name")
	if existing:
		# Keep group currency aligned when no GLEs / still a group
		row = frappe.db.get_value(
			"Account", existing, ["account_currency", "is_group"], as_dict=True
		)
		if row and row.is_group and row.account_currency != currency:
			if not frappe.db.exists("GL Entry", {"account": existing}):
				try:
					frappe.db.set_value(
						"Account", existing, "account_currency", currency, update_modified=False
					)
				except Exception:
					pass
		return existing

	parent = (
		frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Current Liabilities%"], "is_group": 1},
			"name",
			order_by="lft asc",
		)
		or frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Liability", "is_group": 1},
			"name",
			order_by="lft asc",
		)
	)
	if not parent:
		return None

	try:
		acc = frappe.new_doc("Account")
		acc.account_name = account_name_only
		acc.company = company
		acc.parent_account = parent
		acc.is_group = 1
		acc.root_type = "Liability"
		acc.account_type = ""
		acc.account_currency = currency
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		frappe.log_error(title=f"Create Other Payable group {group_name}", message=frappe.get_traceback())
		return frappe.db.get_value("Account", {"name": group_name, "company": company}, "name")


def _ensure_payable_account(company: str, tax_name: str, currency: str | None = None) -> str | None:
	"""Create/get named Other Payable leaf matching expense account currency.

	- Currency follows the expense account (TZS↔TZS, JPY↔JPY) so Fixed JE credits
	  balance in account currency without FX blow-ups.
	- Blank account_type — no Supplier/party on JE lines.
	"""
	if not company or not tax_name:
		return None
	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	currency = (currency or comp_currency).strip() or comp_currency

	base_label = f"{tax_name} Payable".replace("  ", " ").strip()
	if base_label.lower().endswith("payable payable"):
		base_label = base_label[: -len(" Payable")]
	# Prefer Title Case when source label is ALL CAPS (Costing.costing_name)
	if base_label.isupper():
		base_label = (
			base_label.title()
			.replace("Jpy", "JPY")
			.replace("Tzs", "TZS")
			.replace("Usd", "USD")
			.replace("Bl ", "BL ")
		)

	# Disambiguate foreign-currency leaves from existing company-currency ones
	if currency == comp_currency:
		label = base_label
	else:
		label = f"{base_label} {currency}"

	account_name = f"{label} - {abbr}" if abbr else label
	existing = frappe.db.get_value("Account", {"name": account_name, "company": company}, "name")
	parent = _ensure_other_payable_group(company, currency)

	# Also accept a correctly-currency existing "{tax} Payable" without currency suffix
	if not existing and currency != comp_currency:
		plain = f"{base_label} - {abbr}" if abbr else base_label
		plain_row = frappe.db.get_value(
			"Account",
			{"name": plain, "company": company},
			["name", "account_currency"],
			as_dict=True,
		)
		if plain_row and plain_row.account_currency == currency:
			existing = plain_row.name
			account_name = plain

	if existing:
		row = frappe.db.get_value(
			"Account",
			existing,
			["account_type", "account_currency", "parent_account", "is_group"],
			as_dict=True,
		)
		has_gle = frappe.db.exists("GL Entry", {"account": existing})
		wrong_currency = bool(row and row.account_currency and row.account_currency != currency)
		if wrong_currency:
			# Cannot alter currency with (or without safely) — use currency-suffixed leaf
			if currency != comp_currency:
				account_name = f"{base_label} {currency} - {abbr}" if abbr else f"{base_label} {currency}"
			else:
				account_name = f"{base_label} OP - {abbr}" if abbr else f"{base_label} OP"
			existing_alt = frappe.db.get_value("Account", {"name": account_name, "company": company}, "name")
			if existing_alt:
				existing = existing_alt
				row = frappe.db.get_value(
					"Account",
					existing,
					["account_type", "account_currency", "parent_account", "is_group"],
					as_dict=True,
				)
				has_gle = frappe.db.exists("GL Entry", {"account": existing})
				wrong_currency = bool(row and row.account_currency and row.account_currency != currency)
			else:
				existing = None

		if existing and not wrong_currency:
			updates = {}
			if row:
				if row.account_type == "Payable":
					updates["account_type"] = ""
				if parent and row.parent_account != parent and not row.is_group:
					updates["parent_account"] = parent
			if updates:
				try:
					frappe.db.set_value("Account", existing, updates, update_modified=False)
				except Exception:
					pass
			return existing

	if not parent:
		# Do not fall back to company Creditors — Fixed Costing needs named Other Payable
		return None

	try:
		acc = frappe.new_doc("Account")
		acc.account_name = label if currency == comp_currency else f"{base_label} {currency}"
		# When we fell through after wrong_currency, account_name may already include suffix
		if currency != comp_currency and not acc.account_name.endswith(currency):
			acc.account_name = f"{base_label} {currency}"
		acc.company = company
		acc.parent_account = parent
		acc.is_group = 0
		acc.root_type = "Liability"
		acc.account_type = ""  # blank — no Supplier/party on JE lines
		acc.account_currency = currency
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		frappe.log_error(title=f"Create payable {account_name}", message=frappe.get_traceback())
		return frappe.db.get_value("Account", {"name": account_name, "company": company}, "name")


def _expense_account_candidates(company: str, tax_name: str, currency: str, preferred_leaf: str | None = None):
	"""Possible Account.name values for a tax/costing expense leaf."""
	abbr = frappe.db.get_value("Company", company, "abbr") or ""
	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	currency = (currency or comp_currency).strip() or comp_currency
	tax_name = (tax_name or "").strip()
	preferred_leaf = (preferred_leaf or "").strip() or None
	cands = []
	if preferred_leaf:
		cands.append(f"{preferred_leaf} - {abbr}" if abbr else preferred_leaf)
	if currency == comp_currency:
		cands.append(f"{tax_name} - {abbr}" if abbr else tax_name)
	else:
		cands.append(f"{tax_name} {currency} - {abbr}" if abbr else f"{tax_name} {currency}")
		cands.append(f"{tax_name} - {abbr}" if abbr else tax_name)
	# de-dupe preserve order
	seen = set()
	out = []
	for c in cands:
		if c and c not in seen:
			seen.add(c)
			out.append(c)
	return out, currency, abbr, comp_currency


def _ensure_expense_account(
	company: str,
	tax_name: str,
	currency: str,
	account: str | None,
	preferred_leaf: str | None = None,
) -> str | None:
	"""Create/get expense GL for a tax/costing label.

	Company-currency leaves: ``{Name} - ABBR`` (e.g. TRA Duty - JIL).
	Foreign-currency leaves: ``{Name} {CUR} - ABBR`` (e.g. THC JPY - JIL).
	"""
	if account and frappe.db.exists("Account", account):
		return account

	cands, currency, abbr, comp_currency = _expense_account_candidates(
		company, tax_name, currency, preferred_leaf
	)
	for cand in cands:
		if frappe.db.exists("Account", cand):
			return cand

	# Create under Vehicle Import Costing (TZ) or Japan expense group (JPY)
	parent = None
	if currency != comp_currency:
		parent = frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Japan%"], "is_group": 1, "root_type": "Expense"},
			"name",
			order_by="lft asc",
		)
	if not parent:
		parent = frappe.db.get_value(
			"Account",
			{"company": company, "account_name": ["like", "%Vehicle Import Costing%"], "is_group": 1},
			"name",
			order_by="lft asc",
		) or frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Expense", "is_group": 1},
			"name",
			order_by="lft desc",
		)
	if not parent:
		return account

	if currency == comp_currency:
		leaf_name = tax_name
	else:
		leaf_name = preferred_leaf or f"{tax_name} {currency}"
	account_name = f"{leaf_name} - {abbr}" if abbr else leaf_name

	try:
		acc = frappe.new_doc("Account")
		acc.account_name = leaf_name
		acc.company = company
		acc.parent_account = parent
		acc.is_group = 0
		acc.root_type = "Expense"
		acc.account_type = "Expense Account"
		acc.account_currency = currency
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		frappe.log_error(title=f"Create expense {account_name}", message=frappe.get_traceback())
		return frappe.db.get_value("Account", {"name": account_name, "company": company}, "name") or account


def _seed_company_tax_expense_accounts(company: str) -> list[dict]:
	"""Ensure Company.custom_tax_expense_accounts has all DEFAULT rows + GLs.

	Writes child rows directly (avoids Company.on_update quirks). Does not remove
	existing extra rows. Returns tax_rows for Costing sync.
	"""
	if not frappe.db.exists("DocType", "Company Tax Account"):
		return []

	_upsert_tax_rows_direct(company, DEFAULT_TAX_EXPENSE_ACCOUNTS)
	frappe.db.commit()

	return frappe.get_all(
		"Company Tax Account",
		filters={"parent": company, "parenttype": "Company"},
		fields=["tax_name", "account", "account_currency", "idx"],
		order_by="idx asc",
	)


def _upsert_tax_rows_direct(company: str, defaults: list) -> None:
	"""Insert/update Company Tax Account children without saving Company doc."""
	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	existing = {
		(r.tax_name or "").strip().lower(): r
		for r in frappe.get_all(
			"Company Tax Account",
			filters={"parent": company, "parenttype": "Company"},
			fields=["name", "tax_name", "account", "account_currency"],
		)
	}
	for idx, (tax_name, currency, preferred_leaf) in enumerate(defaults, start=1):
		currency = currency or comp_currency
		if currency == "TZS":
			currency = comp_currency
		account = _ensure_expense_account(company, tax_name, currency, None, preferred_leaf)
		acc_currency = _account_currency(account, currency) if account else currency
		key = tax_name.strip().lower()
		row = existing.get(key)
		if row:
			updates = {}
			if (not row.account or not frappe.db.exists("Account", row.account)) and account:
				updates["account"] = account
			if not (row.account_currency or "").strip():
				updates["account_currency"] = acc_currency
			if updates:
				frappe.db.set_value("Company Tax Account", row.name, updates, update_modified=False)
		else:
			child = frappe.get_doc(
				{
					"doctype": "Company Tax Account",
					"parent": company,
					"parenttype": "Company",
					"parentfield": "custom_tax_expense_accounts",
					"tax_name": tax_name,
					"account": account,
					"account_currency": acc_currency,
					"idx": 100 + idx,
				}
			)
			child.insert(ignore_permissions=True)


def _account_currency(account: str, fallback: str | None = None) -> str:
	if account:
		cur = frappe.db.get_value("Account", account, "account_currency")
		if cur:
			return cur
	return fallback or "TZS"


def _resolve_costing_name(tax_name: str, account: str) -> str:
	if account in ACCOUNT_ALIASES:
		return ACCOUNT_ALIASES[account]
	alias = NAME_ALIASES.get((tax_name or "").strip().lower())
	if alias:
		return alias
	return _slug(tax_name)


def _excel_currency(code: str, region: str, account_currency: str) -> str:
	"""Car Costing / Excel: Japan Expected = USD; Tanzania = TZS."""
	if code in EXCEL_JAPAN_USD_CODES or region == "Japan":
		return "USD"
	return account_currency or "TZS"


def _link_payable(company: str, costing_name: str, currency: str, current: str | None) -> str | None:
	"""Ensure a named Other Payable in the given currency; replace Creditors / wrong-currency."""
	label = (costing_name or "").strip()
	if not label:
		return current
	desired = _ensure_payable_account(company, label, currency or "TZS")
	if not desired:
		return current
	if not current:
		return desired
	if current.startswith("Creditors"):
		return desired
	cur_curr = frappe.db.get_value("Account", current, "account_currency")
	if cur_curr and currency and cur_curr != currency:
		return desired
	return current


def execute():
	company = _company()
	if not company:
		return

	# 0) Ensure Company Tax Expense Accounts rows + expense GLs exist
	#    (Japan MKT charges + Tanzania / other Costing expense accounts)
	tax_rows = _seed_company_tax_expense_accounts(company)

	# 1) Sync Tax Expense Accounts → Costing (+ payables)
	if not tax_rows and frappe.db.exists("DocType", "Company Tax Account"):
		tax_rows = frappe.get_all(
			"Company Tax Account",
			filters={"parent": company, "parenttype": "Company"},
			fields=["tax_name", "account", "account_currency", "idx"],
			order_by="idx asc",
		)

	display_base = 200
	for i, row in enumerate(tax_rows or []):
		tax_name = (row.tax_name or "").strip()
		if not tax_name:
			continue
		acc_currency = (row.account_currency or "").strip() or "JPY"
		# Prefer preferred_leaf from DEFAULT list when recreating
		preferred = None
		for tn, cur, leaf in DEFAULT_TAX_EXPENSE_ACCOUNTS:
			if tn.strip().lower() == tax_name.lower():
				preferred = leaf
				if not (row.account_currency or "").strip():
					acc_currency = cur
				break
		account = _ensure_expense_account(
			company,
			tax_name,
			acc_currency,
			(row.account or "").strip() or None,
			preferred_leaf=preferred,
		)
		if not account or not frappe.db.exists("Account", account):
			frappe.log_error(
				title=f"Tax Costing skip {tax_name}",
				message=f"Expense account missing for tax row {tax_name!r} ({row.account!r})",
			)
			continue

		acc_currency = _account_currency(account, acc_currency)
		code = _resolve_costing_name(tax_name, account)
		by_account = frappe.db.get_value("Costing", {"account": account}, "name")
		if by_account:
			code = by_account

		region = "Japan" if acc_currency == "JPY" else "Tanzania"
		currency = _excel_currency(code, region, acc_currency)

		payable_label = tax_name
		if frappe.db.exists("Costing", code):
			existing_name = frappe.db.get_value("Costing", code, "costing_name")
			if existing_name:
				payable_label = existing_name.title()
		payable = _ensure_payable_account(company, payable_label, acc_currency)

		by_vehicle_labels = {"inspection", "jpn expense", "repair cost", "car expense"}
		scope = "By Vehicle" if tax_name.strip().lower() in by_vehicle_labels else "By BL Equal"

		payload = {
			"account": account,
			"payable_account": payable,
			"currency": currency,
			"region": region,
			"allocation_scope": scope,
			"disabled": 0,
			"display_order": display_base + i,
		}

		if code in ("japan_cost", "inspection", "forwarding") and frappe.db.exists("Costing", code):
			existing_mode = frappe.db.get_value("Costing", code, "entry_mode")
			if existing_mode:
				payload["entry_mode"] = existing_mode
		else:
			payload["entry_mode"] = "Variable"
			if not frappe.db.exists("Costing", code):
				payload["costing_name"] = tax_name.upper()

		if frappe.db.exists("Costing", code):
			frappe.db.set_value("Costing", code, payload, update_modified=False)
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Costing",
					"costing_code": code,
					"costing_name": tax_name.upper(),
					**payload,
				}
			)
			doc.insert(ignore_permissions=True)

	# 2) Japan Excel sense: Japan Costing.currency = USD;
	#    payable currency always matches expense account (JPY↔JPY, TZS↔TZS)
	for c in frappe.get_all(
		"Costing",
		filters={"disabled": 0},
		fields=["name", "region", "currency", "account", "costing_name", "payable_account"],
	):
		if c.region == "Japan":
			if c.currency != "USD":
				frappe.db.set_value("Costing", c.name, "currency", "USD", update_modified=False)
		else:
			acc_cur = _account_currency(c.account, c.currency or "TZS")
			if c.account and c.currency != acc_cur:
				frappe.db.set_value("Costing", c.name, "currency", acc_cur, update_modified=False)

		exp_curr = _account_currency(c.account, "TZS") if c.account else (
			frappe.db.get_value("Company", company, "default_currency") or "TZS"
		)
		new_pay = _link_payable(company, c.costing_name, exp_curr, c.payable_account)
		if new_pay and new_pay != c.payable_account:
			frappe.db.set_value("Costing", c.name, "payable_account", new_pay, update_modified=False)
		elif c.payable_account:
			_ensure_payable_account(company, c.costing_name or c.name, exp_curr)

	# 3) Fold Custom Field property setters into the Custom Field itself
	_fold_custom_field_property_setters()
	_ensure_demo_exchange_rates()

	frappe.clear_cache(doctype="Costing")
	frappe.clear_cache(doctype="Item")

	if frappe.db.exists("DocType", "Car Costing"):
		frappe.db.sql("UPDATE `tabCar Costing` SET docstatus = 0 WHERE docstatus = 1")

	frappe.db.commit()


def _fold_custom_field_property_setters():
	"""Move Custom Field property setters onto Custom Field rows; delete those PS."""
	targets = [
		("Item", "custom_chassis_no", "in_list_view", 1),
		("Item", "custom_chassis_no", "in_standard_filter", 1),
	]
	for dt, fieldname, prop, value in targets:
		cf_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": fieldname}, "name")
		if cf_name:
			frappe.db.set_value("Custom Field", cf_name, prop, value, update_modified=False)
		ps_name = f"{dt}-{fieldname}-{prop}"
		if frappe.db.exists("Property Setter", ps_name):
			frappe.delete_doc("Property Setter", ps_name, ignore_permissions=True, force=True)


def _ensure_currency_exchange(from_currency, to_currency, rate):
	"""Ensure a buying Currency Exchange exists (idempotent)."""
	if not from_currency or not to_currency or from_currency == to_currency or not rate:
		return
	existing = frappe.db.get_value(
		"Currency Exchange",
		{"from_currency": from_currency, "to_currency": to_currency, "for_buying": 1},
		["name", "exchange_rate"],
		as_dict=True,
	)
	if existing:
		return
	try:
		ce = frappe.new_doc("Currency Exchange")
		ce.from_currency = from_currency
		ce.to_currency = to_currency
		ce.exchange_rate = rate
		ce.for_buying = 1
		ce.for_selling = 1
		ce.date = frappe.utils.getdate("2024-01-01")
		ce.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Currency Exchange {from_currency}->{to_currency}", message=frappe.get_traceback())


def _ensure_demo_exchange_rates():
	"""Ensure USD↔TZS / USD↔JPY exist so Car Costing can auto-pick (Excel sense)."""
	# Prefer deriving USD→TZS from existing JPY→TZS × USD→JPY if available
	jpy_tzs = frappe.db.get_value(
		"Currency Exchange",
		{"from_currency": "JPY", "to_currency": "TZS", "for_buying": 1},
		"exchange_rate",
		order_by="date desc",
	)
	# Excel sample defaults when nothing exists yet
	usd_jpy = 155.0
	usd_tzs = flt(jpy_tzs) * usd_jpy if flt(jpy_tzs) else 2700.0
	_ensure_currency_exchange("USD", "JPY", usd_jpy)
	_ensure_currency_exchange("USD", "TZS", usd_tzs)
	if flt(jpy_tzs):
		_ensure_currency_exchange("JPY", "USD", flt(1.0 / usd_jpy))
