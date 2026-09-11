# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Relabel Item.custom_price → Purchase Price."""

import frappe


def execute():
	name = "Item-custom_price"
	if frappe.db.exists("Custom Field", name):
		frappe.db.set_value("Custom Field", name, "label", "Purchase Price", update_modified=False)
	# Property Setter field_order doesn't store labels; clear Item cache
	frappe.clear_cache(doctype="Item")
	frappe.db.commit()
