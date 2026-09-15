# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Align Fixed Costing payables to expense account currency.

Re-runnable: creates Other Payable / Other Payable JPY groups, ensures named
payable leaves match the expense account currency (JPY↔JPY, TZS↔TZS), blank
account_type (no Supplier party), and relinks Costing.payable_account.
"""

from __future__ import annotations

import frappe

from vsd_jan_integration.patches.seed_costing_from_tax_accounts import (
	_account_currency,
	_company,
	_ensure_other_payable_group,
	_ensure_payable_account,
	_link_payable,
)


def execute():
	company = _company()
	if not company:
		return

	comp_currency = frappe.db.get_value("Company", company, "default_currency") or "TZS"
	_ensure_other_payable_group(company, comp_currency)

	for c in frappe.get_all(
		"Costing",
		filters={"disabled": 0},
		fields=["name", "costing_name", "account", "payable_account"],
	):
		label = c.costing_name or c.name
		exp_curr = _account_currency(c.account, comp_currency) if c.account else comp_currency
		_ensure_other_payable_group(company, exp_curr)
		pay = _link_payable(company, label, exp_curr, c.payable_account)
		if pay and pay != c.payable_account:
			frappe.db.set_value("Costing", c.name, "payable_account", pay, update_modified=False)

	frappe.clear_cache(doctype="Costing")
	frappe.clear_cache(doctype="Account")
	frappe.db.commit()
