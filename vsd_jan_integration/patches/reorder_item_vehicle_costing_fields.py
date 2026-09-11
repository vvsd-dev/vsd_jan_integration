# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Reorder Item Vehicle Specification (3-col) + Costing tab; fix Property Setter field_order."""

from __future__ import annotations

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ORDER_BLOCK = [
	"custom_vehicle_specification_tab",
	"custom_vehicle_specification",
	"custom_exhibition_no",
	"custom_purchase_company",
	"custom_new_stock_id",
	"custom_chassis_no",
	"custom_model_code",
	"custom_engine_code",
	"custom_drive_type",
	"custom_doors",
	"custom_color",
	"custom_mukechi",
	"custom_price",
	"custom_m3",
	"custom_col_break_2",
	"custom_auction_company",
	"custom_purchase_date",
	"custom_bl",
	"custom_maker",
	"custom_manufactured_year",
	"custom_engine_cc",
	"custom_transmission",
	"custom_seats",
	"custom_interior_color",
	"custom_bid_by",
	"custom_territory",
	"custom_column_break_mfqlr",
	"custom_auction_no",
	"custom_days_since_purchase",
	"custom_container_no",
	"custom_model",
	"custom_gradeclass",
	"custom_fuel_type",
	"custom_steering",
	"custom_mileage",
	"custom_loaded_docs_status",
	"custom_vehicle_details_section",
	"custom_highest_bids_remarks",
	"custom_costing_tab",
	"custom_costing_summary_section",
	"custom_exchange_rate",
	"custom_total_expected_expense",
	"custom_total_actual_expense",
	"custom_costing_col_2",
	"custom_cost",
	"custom_selling_price",
	"custom_profit_usd",
	"custom_costing_col_3",
	"custom_last_car_costing",
	"custom_costing_lines_section",
	"custom_tz_costing",
	"custom_japan_costing",
]

DEAD_BREAKS = ["custom_col_break_1", "custom_column_break_webz4", "custom_column_break_v1p9w"]

COSTING_FIELDS = [
	{
		"fieldname": "custom_costing_tab",
		"label": "Costing",
		"fieldtype": "Tab Break",
		"insert_after": "custom_highest_bids_remarks",
	},
	{
		"fieldname": "custom_costing_summary_section",
		"label": "Cost Summary",
		"fieldtype": "Section Break",
		"insert_after": "custom_costing_tab",
	},
	{
		"fieldname": "custom_exchange_rate",
		"label": "Exchange Rate (TZS/USD)",
		"fieldtype": "Float",
		"insert_after": "custom_costing_summary_section",
	},
	{
		"fieldname": "custom_total_expected_expense",
		"label": "Total Expected Expense",
		"fieldtype": "Currency",
		"insert_after": "custom_exchange_rate",
		"read_only": 1,
	},
	{
		"fieldname": "custom_total_actual_expense",
		"label": "Total Actual Expense",
		"fieldtype": "Currency",
		"insert_after": "custom_total_expected_expense",
		"read_only": 1,
	},
	{
		"fieldname": "custom_costing_col_2",
		"fieldtype": "Column Break",
		"insert_after": "custom_total_actual_expense",
	},
	{
		"fieldname": "custom_cost",
		"label": "Cost (TSH)",
		"fieldtype": "Currency",
		"insert_after": "custom_costing_col_2",
		"read_only": 1,
	},
	{
		"fieldname": "custom_selling_price",
		"label": "Selling Price (TSH)",
		"fieldtype": "Currency",
		"insert_after": "custom_cost",
		"read_only": 1,
	},
	{
		"fieldname": "custom_profit_usd",
		"label": "Profit (USD)",
		"fieldtype": "Currency",
		"insert_after": "custom_selling_price",
		"read_only": 1,
	},
	{
		"fieldname": "custom_costing_col_3",
		"fieldtype": "Column Break",
		"insert_after": "custom_profit_usd",
	},
	{
		"fieldname": "custom_last_car_costing",
		"label": "Last Car Costing",
		"fieldtype": "Link",
		"options": "Car Costing",
		"insert_after": "custom_costing_col_3",
		"read_only": 1,
	},
	{
		"fieldname": "custom_costing_lines_section",
		"label": "Costing Lines",
		"fieldtype": "Section Break",
		"insert_after": "custom_last_car_costing",
	},
	{
		"fieldname": "custom_tz_costing",
		"label": "Tanzania Costing (Expected / Actual)",
		"fieldtype": "Table",
		"options": "Item Costing Line",
		"insert_after": "custom_costing_lines_section",
		"read_only": 1,
	},
	{
		"fieldname": "custom_japan_costing",
		"label": "Japan Costing (Expected / Actual)",
		"fieldtype": "Table",
		"options": "Item Costing Line",
		"insert_after": "custom_tz_costing",
		"read_only": 1,
	},
]


def execute():
	frappe.flags.in_patch = True

	create_custom_fields(
		{"Item": [{**f, "module": "VSD Jan International Customization"} for f in COSTING_FIELDS]},
		update=True,
	)

	# Delete obsolete column breaks. Do NOT convert them to Data — that makes
	# ORM INSERT expect DB columns that never existed for layout fields.
	for fn in DEAD_BREAKS:
		name = f"Item-{fn}"
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)

	prev = "custom_sunroof"
	for fn in ORDER_BLOCK:
		name = f"Item-{fn}"
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, "insert_after", prev, update_modified=False)
			prev = fn

	frappe.db.set_value(
		"Custom Field", "Item-custom_vehicle_specification", "label", "Identification & Purchase", update_modified=False
	)
	frappe.db.set_value(
		"Custom Field", "Item-custom_vehicle_details_section", "label", "Notes", update_modified=False
	)
	frappe.db.set_value(
		"Custom Field",
		"Item-custom_tz_costing",
		"label",
		"Tanzania Costing (Expected / Actual)",
		update_modified=False,
	)
	frappe.db.set_value(
		"Custom Field",
		"Item-custom_japan_costing",
		"label",
		"Japan Costing (Expected / Actual)",
		update_modified=False,
	)

	ps_name = "Item-main-field_order"
	if frappe.db.exists("Property Setter", ps_name):
		ps = frappe.get_doc("Property Setter", ps_name)
		order = json.loads(ps.value)
		remove = set(ORDER_BLOCK) | set(DEAD_BREAKS)
		order = [f for f in order if f not in remove]
		anchor = "custom_sunroof" if "custom_sunroof" in order else None
		i = order.index(anchor) + 1 if anchor else len(order)
		block = [f for f in ORDER_BLOCK if frappe.db.exists("Custom Field", f"Item-{f}")]
		order[i:i] = block
		ps.value = json.dumps(order)
		ps.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Item")
	frappe.db.commit()
