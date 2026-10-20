# Copyright (c) 2026, VV Systems Developer LTD and contributors


def run():
	import os

	import frappe
	from frappe.modules.import_file import import_file_by_path

	path = frappe.get_app_path(
		"vsd_jan_integration",
		"vsd_jan_international_customization",
		"report",
		"jan_sale_report",
		"jan_sale_report.json",
	)
	print("PATH", path, os.path.exists(path))
	import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)
	frappe.db.commit()
	print("EXISTS", frappe.db.exists("Report", "Jan Sale Report"))

	if not frappe.db.get_value(
		"Company", "Jan International Limited", "custom_trade_in_control_account"
	):
		frappe.db.set_value(
			"Company",
			"Jan International Limited",
			"custom_trade_in_control_account",
			"Stock Adjustment - JIL",
		)
		frappe.db.commit()
		print("SET_TRADE_IN_ACCT")

	from vsd_jan_integration.vsd_jan_international_customization.utils.selling_costing import (
		process_sales_invoice_selling_costing,
	)

	for name in ("ACC-SINV-2026-00001", "ACC-SINV-2026-00002"):
		si = frappe.get_doc("Sales Invoice", name)
		try:
			process_sales_invoice_selling_costing(si)
			print("SELLING_OK", name)
		except Exception as e:
			print("SELLING_FAIL", name, e)
	frappe.db.commit()

	from vsd_jan_integration.api.sale_report import execute

	_cols, data = execute({"currency": "USD"})
	for r in data:
		print(
			"USD",
			r["chassis"],
			"duty",
			round(r["duty"], 2),
			"expense",
			round(r["expense"], 2),
			"sale",
			round(r["sale_price"], 2),
		)
	return {"ok": True, "rows": len(data)}
