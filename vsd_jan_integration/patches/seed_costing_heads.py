# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Seed Costing Heads for Car Costing (Expense List) + create related GL accounts."""

import frappe

COMPANY = "Jan International Limited"
ABBR = "JIL"
PARENT_GROUP = f"Direct Expenses - {ABBR}"
COSTING_GROUP = f"Vehicle Import Costing - {ABBR}"

# Obsolete heads left from earlier iterations — disable, do not delete
OBSOLETE_CODES = [
	"m3",
	"duty_usd",
	"total_exp_tsh",
	"total_exp_usd",
	"port_to_yard",
	"repairing_charges",
]

COSTING_HEADS = [
	# Tanzania (TZS) — Purchase
	{
		"costing_code": "tra_duty",
		"costing_name": "TRA DUTY",
		"region": "Tanzania",
		"entry_mode": "Variable",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 10,
		"currency": "TZS",
		"account_name": "TRA Duty",
	},
	{
		"costing_code": "clearing_container",
		"costing_name": "CLEARING CONTAINER",
		"region": "Tanzania",
		"entry_mode": "Fixed",
		"allocation_scope": "By BL Equal",
		"costing_side": "Purchase",
		"display_order": 20,
		"currency": "TZS",
		"default_projected_amount": 112350,
		"account_name": "Clearing Container",
	},
	{
		"costing_code": "ex_bond",
		"costing_name": "EX-BOND",
		"region": "Tanzania",
		"entry_mode": "Fixed",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 30,
		"currency": "TZS",
		"default_projected_amount": 139314,
		"account_name": "Ex-Bond",
	},
	{
		"costing_code": "service",
		"costing_name": "SERVICE",
		"region": "Tanzania",
		"entry_mode": "Fixed",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 40,
		"currency": "TZS",
		"default_projected_amount": 50000,
		"account_name": "Car Service",
	},
	{
		"costing_code": "wharfage",
		"costing_name": "WHARFAGE",
		"region": "Tanzania",
		"entry_mode": "Formula",
		"allocation_scope": "By Formula",
		"costing_side": "Purchase",
		"display_order": 50,
		"currency": "TZS",
		"formula": "{line.tra_duty} * 0.07",
		"depends_on": "tra_duty",
		"account_name": "Wharfage",
	},
	{
		"costing_code": "driver_port_to_yard",
		"costing_name": "DRIVER PORT TO YARD",
		"region": "Tanzania",
		"entry_mode": "Fixed",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 60,
		"currency": "TZS",
		"default_projected_amount": 35000,
		"account_name": "Driver Port to Yard",
	},
	{
		"costing_code": "fuel_port_to_yard",
		"costing_name": "FUEL PORT TO YARD",
		"region": "Tanzania",
		"entry_mode": "Fixed",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 70,
		"currency": "TZS",
		"default_projected_amount": 0,
		"account_name": "Fuel Port to Yard",
	},
	{
		"costing_code": "tpa",
		"costing_name": "TPA",
		"region": "Tanzania",
		"entry_mode": "Variable",
		"allocation_scope": "By BL Equal",
		"costing_side": "Purchase",
		"display_order": 80,
		"currency": "TZS",
		"account_name": "TPA",
	},
	{
		"costing_code": "bond_insurance",
		"costing_name": "BOND INSURANCE",
		"region": "Tanzania",
		"entry_mode": "Fixed",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 90,
		"currency": "TZS",
		"default_projected_amount": 50000,
		"account_name": "Bond Insurance",
	},
	{
		"costing_code": "repairing_charges_local",
		"costing_name": "REPAIRING CHARGES Local",
		"region": "Tanzania",
		"entry_mode": "Variable",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 100,
		"currency": "TZS",
		"account_name": "Repairing Charges Local",
	},
	# Tanzania (TZS) — Selling (1 BL COST.xlsx AM / AO from AS selling price)
	{
		"costing_code": "city_levy_tax",
		"costing_name": "CITY LEVY TAX",
		"region": "Tanzania",
		"entry_mode": "Formula",
		"allocation_scope": "By Vehicle",
		"costing_side": "Selling",
		"display_order": 105,
		"currency": "TZS",
		"formula": "{header.expected_selling_price} * 0.003",
		"account_name": "City Levy Tax",
	},
	{
		"costing_code": "vat",
		"costing_name": "VAT",
		"region": "Tanzania",
		"entry_mode": "Formula",
		"allocation_scope": "By Vehicle",
		"costing_side": "Selling",
		"display_order": 106,
		"currency": "TZS",
		# Excel: VAT 18% = price×18%; VAT cost = that × 20%
		"formula": "{header.expected_selling_price} * 0.18 * 0.2",
		"account_name": "VAT Costing",
	},
	# Japan (USD) — Purchase
	{
		"costing_code": "japan_cost",
		"costing_name": "JAPAN COST",
		"region": "Japan",
		"entry_mode": "Fixed",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 110,
		"currency": "USD",
		"default_projected_amount": 261,
		# Prefer live MKT JE account (JPN Expense) when present
		"account_name": "JPN Expense JPY",
		"fallback_account_name": "Japan Cost",
	},
	{
		"costing_code": "inspection",
		"costing_name": "INSPECTION",
		"region": "Japan",
		"entry_mode": "Fixed",
		"allocation_scope": "By Vehicle",
		"costing_side": "Purchase",
		"display_order": 120,
		"currency": "USD",
		"default_projected_amount": 170,
		# Prefer live MKT JE account when present
		"account_name": "Inspection JPY",
		"fallback_account_name": "Inspection",
	},
	{
		"costing_code": "icd",
		"costing_name": "ICD",
		"region": "Japan",
		"entry_mode": "Variable",
		"allocation_scope": "By BL M3",
		"costing_side": "Purchase",
		"display_order": 130,
		"currency": "USD",
		"account_name": "ICD",
	},
	{
		"costing_code": "shipping_line",
		"costing_name": "SHIPPING LINE",
		"region": "Japan",
		"entry_mode": "Variable",
		"allocation_scope": "By BL M3",
		"costing_side": "Purchase",
		"display_order": 140,
		"currency": "USD",
		"account_name": "Shipping Line",
	},
]


def _ensure_account(account_name):
	account = f"{account_name} - {ABBR}"
	if frappe.db.exists("Account", account):
		return account

	if not frappe.db.exists("Account", COSTING_GROUP):
		if not frappe.db.exists("Account", PARENT_GROUP):
			frappe.throw(f"Parent account group missing: {PARENT_GROUP}")
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "Vehicle Import Costing",
				"is_group": 1,
				"company": COMPANY,
				"parent_account": PARENT_GROUP,
				"root_type": "Expense",
			}
		).insert(ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"is_group": 0,
			"company": COMPANY,
			"parent_account": COSTING_GROUP,
			"root_type": "Expense",
			"account_type": "Expense Account",
		}
	).insert(ignore_permissions=True)
	return account


def execute():
	# Migrate old sequence -> display_order if column still has data
	if frappe.db.has_column("Costing", "sequence") and frappe.db.has_column("Costing", "display_order"):
		frappe.db.sql(
			"""
			UPDATE `tabCosting`
			SET display_order = COALESCE(NULLIF(display_order, 0), sequence, 0)
			WHERE IFNULL(display_order, 0) = 0 AND IFNULL(sequence, 0) != 0
			"""
		)

	for code in OBSOLETE_CODES:
		if frappe.db.exists("Costing", code):
			frappe.db.set_value("Costing", code, "disabled", 1)

	for row in COSTING_HEADS:
		data = dict(row)
		account_name = data.pop("account_name", None)
		fallback = data.pop("fallback_account_name", None)
		if account_name:
			preferred = f"{account_name} - {ABBR}"
			if frappe.db.exists("Account", preferred):
				data["account"] = preferred
			elif fallback:
				data["account"] = _ensure_account(fallback)
			else:
				data["account"] = _ensure_account(account_name)

		# Ensure named Other Payable for every active head (Fixed / Formula / Variable).
		# Creates GL under Other Payable when missing — same helper as tax-accounts patch.
		if not data.get("payable_account"):
			existing_pay = _existing_named_payable_for_head(data)
			if existing_pay:
				data["payable_account"] = existing_pay
			else:
				created_pay = _create_named_payable_for_head(data)
				if created_pay:
					data["payable_account"] = created_pay

		if frappe.db.exists("Costing", data["costing_code"]):
			# Keep document name = costing_code; set labels via db_set to avoid rename side-effects
			name = data["costing_code"]
			for key, val in data.items():
				if key == "costing_code":
					continue
				# Never overwrite a user-selected payable_account with seed invent
				if key == "payable_account":
					cur_pay = frappe.db.get_value("Costing", name, "payable_account") or ""
					if cur_pay and frappe.db.exists("Account", cur_pay):
						continue
				frappe.db.set_value("Costing", name, key, val, update_modified=False)
			frappe.db.set_value("Costing", name, "disabled", 0, update_modified=False)
		else:
			doc = frappe.get_doc({"doctype": "Costing", **data})
			doc.insert(ignore_permissions=True)

	# Backfill costing_side = Purchase on any legacy heads missing the field value
	if frappe.db.has_column("Costing", "costing_side"):
		frappe.db.sql(
			"""
			UPDATE `tabCosting`
			SET costing_side = 'Purchase'
			WHERE IFNULL(costing_side, '') = ''
			"""
		)

	frappe.db.commit()
	frappe.clear_cache(doctype="Costing")


def _existing_named_payable_for_head(data):
	"""Return an already-existing named payable Account if present."""
	label = (data.get("costing_name") or data.get("costing_code") or "").strip()
	if not label:
		return None
	words = label.replace("_", " ").split()
	title = " ".join(w.capitalize() for w in words)
	for candidate in (
		f"{title} Payable - {ABBR}",
		f"{label.title()} Payable - {ABBR}",
		f"{label} Payable - {ABBR}",
	):
		if frappe.db.exists("Account", candidate):
			return candidate
	return None


def _create_named_payable_for_head(data):
	"""Create named Other Payable for this Costing head (currency = expense account)."""
	from vsd_jan_integration.patches.seed_costing_from_tax_accounts import (
		_ensure_payable_account,
		_account_currency,
	)

	label = (data.get("costing_name") or data.get("costing_code") or "").strip()
	if not label:
		return None
	company = data.get("company") or COMPANY
	exp = data.get("account")
	currency = _account_currency(exp, data.get("currency") or "TZS") if exp else (
		data.get("currency") or "TZS"
	)
	return _ensure_payable_account(company, label, currency)
