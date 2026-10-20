# Copyright (c) 2026, VV Systems Developer LTD and contributors
# Transient verify: SI-only selling on Jan BL Costing.


def run():
	import frappe
	from frappe.utils import flt
	from vsd_jan_integration.api import costing_report as cr

	out = {"si": None, "no_si": []}

	si = frappe.get_doc("Sales Invoice", "ACC-SINV-2026-00001")
	out["si"] = {
		"name": si.name,
		"docstatus": si.docstatus,
		"customer": si.customer,
		"lines": [],
	}
	for row in si.items:
		chassis = frappe.db.get_value("Item", row.item_code, "custom_chassis_no")
		esp = frappe.db.get_value("Car Costing", {"item": row.item_code}, "expected_selling_price")
		item_sell = (
			frappe.db.get_value("Item", row.item_code, "custom_selling_price")
			if frappe.db.has_column("Item", "custom_selling_price")
			else None
		)
		si_base = flt(row.base_rate) or flt(row.rate) * (flt(si.conversion_rate) or 1)
		report_row = None
		_cols, data = cr.execute({"currency": "TZS", "chassis": chassis or ""})
		for r in data:
			if r.get("item") == row.item_code or (chassis and r.get("chassis") == chassis):
				report_row = {
					"chassis": r.get("chassis"),
					"selling": r.get("selling"),
					"vat_18": r.get("vat_18"),
					"city_levy_tax": r.get("city_levy_tax"),
					"vat": r.get("vat"),
					"total_exp": r.get("total_exp"),
				}
				break
		line = {
			"item": row.item_code,
			"chassis": chassis,
			"base_rate": flt(row.base_rate),
			"rate": flt(row.rate),
			"si_base": si_base,
			"esp": flt(esp),
			"item_sell": flt(item_sell),
			"expect_vat18": si_base * 0.18,
			"expect_levy": si_base * 0.003,
			"expect_vat_cost": si_base * 0.18 * 0.2,
			"report": report_row,
		}
		out["si"]["lines"].append(line)
		print("SI_LINE", line)

	no_si = frappe.db.sql(
		"""
		SELECT cc.chassis_no, cc.item, cc.expected_selling_price,
			IFNULL((SELECT custom_selling_price FROM tabItem WHERE name=cc.item), 0) as item_sell
		FROM `tabCar Costing` cc
		WHERE IFNULL(cc.expected_selling_price, 0) > 0
		AND NOT EXISTS (
			SELECT 1 FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
			WHERE sii.item_code = cc.item
		)
		LIMIT 3
		""",
		as_dict=True,
	)
	for c in no_si:
		_cols, data = cr.execute({"currency": "TZS", "chassis": c.chassis_no})
		rep = None
		for r in data:
			if r.get("chassis") == c.chassis_no:
				rep = {
					"selling": r.get("selling"),
					"vat_18": r.get("vat_18"),
					"city_levy_tax": r.get("city_levy_tax"),
					"vat": r.get("vat"),
				}
				break
		row = {
			"chassis": c.chassis_no,
			"item": c.item,
			"esp": flt(c.expected_selling_price),
			"item_sell": flt(c.item_sell),
			"report": rep,
		}
		out["no_si"].append(row)
		print("NO_SI", row)
		assert flt((rep or {}).get("selling")) == 0
		assert flt((rep or {}).get("vat_18")) == 0

	# Smoke no-SI assertions
	from vsd_jan_integration.scripts._smoke_actual_only_bl import run as smoke

	smoke_out = smoke()
	out["smoke"] = smoke_out
	print("OK_VERIFY")
	return out
