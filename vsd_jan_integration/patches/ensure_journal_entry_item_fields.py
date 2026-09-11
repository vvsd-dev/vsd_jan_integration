# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Ensure Journal Entry custom_item / custom_chassis_no exist."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	create_custom_fields(
		{
			"Journal Entry": [
				{
					"fieldname": "custom_item",
					"label": "Item",
					"fieldtype": "Link",
					"options": "Item",
					"insert_after": "import_file",
					"description": "Vehicle Item for this JE. IFCV maps By Vehicle expenses using this first.",
					"module": "VSD Jan International Customization",
				},
				{
					"fieldname": "custom_chassis_no",
					"label": "Chassis No",
					"fieldtype": "Data",
					"insert_after": "custom_item",
					"fetch_from": "custom_item.custom_chassis_no",
					"read_only": 1,
					"module": "VSD Jan International Customization",
				},
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Journal Entry")
	frappe.db.commit()
