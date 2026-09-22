# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Seed Costing Settings defaults after install/migrate."""

import frappe


def execute():
	if not frappe.db.exists("DocType", "Costing Settings"):
		return
	doc = frappe.get_single("Costing Settings")
	changed = False
	if doc.create_landed_cost_voucher is None:
		doc.create_landed_cost_voucher = 1
		changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
