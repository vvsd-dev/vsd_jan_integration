# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import unittest
import os
import json
import openpyxl
import frappe
from frappe.tests.utils import FrappeTestCase
from vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer import (
	detect_excel_format,
	parse_mkt_statement_excel,
	process_mkt_statement,
	find_item_by_chassis,
	ensure_supplier,
)


def create_test_item(item_code, chassis_no):
	if not frappe.db.exists("Item", item_code):
		doc = frappe.new_doc("Item")
		doc.item_code = item_code
		doc.item_name = item_code
		doc.item_group = "All Item Groups"
		doc.stock_uom = "Nos"
		doc.custom_chassis_no = chassis_no
		doc.insert(ignore_permissions=True)
		frappe.db.commit()



class TestItemExcelImporter(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()
		frappe.clear_cache()
		ensure_supplier("JAN JAPAN")
		# Cancel and delete any existing test Purchase Invoices from prior runs
		# Clean up any test Journal Entries created in prior runs
		jvs = frappe.db.get_all("Journal Entry", filters={"cheque_no": ["in", ["INV-CIF-001", "INV-FOB-002", "INV-RORO-003"]]}, pluck="name")
		for jv_name in jvs:
			try:
				frappe.db.delete("Journal Entry Account", {"parent": jv_name})
				frappe.db.delete("GL Entry", {"voucher_no": jv_name})
				frappe.db.delete("Journal Entry", {"name": jv_name})
			except Exception:
				pass

		# Clean up any test Import Files created in prior runs
		for if_num in (
			"INV-CIF-001", "INV-FOB-002", "INV-TEST-003", "INV-RORO-003",
			"MEDUW-BL-12345", "RORO-BL-88888", "BL-TEST-999",
			"INV-CIF-001 - MEDUW-BL-12345", "INV-RORO-003 - RORO-BL-88888", "INV-TEST-003 - BL-TEST-999"
		):
			if frappe.db.exists("Import File", if_num):
				try:
					frappe.db.delete("Import File", {"name": if_num})
				except Exception:
					pass

		for bill_no in ("INV-CIF-001", "INV-FOB-002", "INV-TEST-003", "INV-RORO-003"):
			pis = frappe.db.get_all("Purchase Invoice", filters={"bill_no": bill_no}, pluck="name")
			for pi_name in pis:
				lcvs = frappe.db.get_all("Landed Cost Purchase Receipt", filters={"receipt_document": pi_name}, pluck="parent")
				for lcv_name in lcvs:
					try:
						frappe.db.delete("Landed Cost Item", {"parent": lcv_name})
						frappe.db.delete("Landed Cost Taxes and Charges", {"parent": lcv_name})
						frappe.db.delete("Landed Cost Purchase Receipt", {"parent": lcv_name})
						frappe.db.delete("Landed Cost Voucher", {"name": lcv_name})
					except Exception:
						pass
				try:
					frappe.db.delete("Purchase Invoice Item", {"parent": pi_name})
					frappe.db.delete("Purchase Taxes and Charges", {"parent": pi_name})
					frappe.db.delete("GL Entry", {"voucher_no": pi_name})
					frappe.db.delete("Stock Ledger Entry", {"voucher_no": pi_name})
					frappe.db.delete("Purchase Invoice", {"name": pi_name})
				except Exception:
					pass
		frappe.db.commit()

	def test_cif_mkt_statement_processing(self):
		chassis_1 = "TEST-CIF-CHASSIS-001"
		item_code_1 = "TOYOTA - TEST-CIF-CHASSIS-001"
		create_test_item(item_code_1, chassis_1)

		chassis_2 = "TEST-CIF-CHASSIS-002"
		item_code_2 = "TOYOTA - TEST-CIF-CHASSIS-002"
		create_test_item(item_code_2, chassis_2)

		file_path = os.path.abspath("test_cif_statement.xlsx")
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.title = "Statement"

		# Table 0: Header Info
		ws.append(["Sr#", "Invoice Date", "Invoice No.", "BL/SW", "SUR", "Week"])
		ws.append([1, "04-02-2026", "INV-CIF-001", "MEDUW-BL-12345", "N", "WK6-26"])
		ws.append([])

		# Table 1: Full Invoice Value
		ws.append(["Full Invoice Value - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Container No.", "THC", "Forwarding", "Freight", "Inspection", "JPN Expense", "Repair Cost", "Car Expense", "Vanning", "Transportation", "Freight & Other", "Cars", "Car Value", "Cont. Other Value", "Cont. Price", "Total", "Invoice No."])
		ws.append(["MSDU1112223", 5000, 10000, 15000, 2000, 0, 0, 0, 3000, 0, 0, 1, 500000, 0, 535000, 535000, "INV-CIF-001"])
		ws.append(["MSDU4445556", 6000, 12000, 18000, 1000, 0, 0, 0, 4000, 0, 0, 1, 400000, 0, 441000, 441000, "INV-CIF-001"])
		ws.append([])

		# Table 2: Invoice Cars
		ws.append(["Invoice Cars - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice No.", "Invoice Date"])
		ws.append([1, "999001", chassis_1, 500000, "INV-CIF-001", "04-02-2026"])
		ws.append([2, "999002", chassis_2, 400000, "INV-CIF-001", "04-02-2026"])
		ws.append([3, "999003", "MISSING-CHASSIS-999", 300000, "INV-CIF-002", "04-02-2026"])

		wb.save(file_path)

		try:
			self.assertEqual(detect_excel_format(file_path), "MKT Statement")

			res = process_mkt_statement(file_path, create_ifcv=False)
			self.assertTrue(res["created_pi"] + res["updated_pi"] >= 1)

			# Verify Item updates
			cont_1 = frappe.db.get_value("Item", item_code_1, "custom_container_no")
			bl_1 = frappe.db.get_value("Item", item_code_1, "custom_bl")
			price_1 = frappe.db.get_value("Item", item_code_1, "custom_price")
			self.assertEqual(cont_1, "MSDU1112223")
			self.assertEqual(bl_1, "MEDUW-BL-12345")
			self.assertEqual(float(price_1), 500000.0)

			cont_2 = frappe.db.get_value("Item", item_code_2, "custom_container_no")
			bl_2 = frappe.db.get_value("Item", item_code_2, "custom_bl")
			price_2 = frappe.db.get_value("Item", item_code_2, "custom_price")
			self.assertEqual(cont_2, "MSDU4445556")
			self.assertEqual(bl_2, "MEDUW-BL-12345")
			self.assertEqual(float(price_2), 400000.0)

			# Verify Purchase Invoice for INV-CIF-001 was created
			pi_name = frappe.db.get_value("Purchase Invoice", {"bill_no": "INV-CIF-001"}, "name")
			self.assertTrue(pi_name)
			pi_doc = frappe.get_doc("Purchase Invoice", pi_name)

			# Taxes table MUST be empty on Purchase Invoice
			self.assertEqual(len(pi_doc.taxes), 0)

			# Verify Journal Entry created for expense charges
			jv_name = frappe.db.get_value("Journal Entry", {"cheque_no": "INV-CIF-001"}, "name")
			self.assertTrue(jv_name)
			jv_doc = frappe.get_doc("Journal Entry", jv_name)
			self.assertEqual(str(jv_doc.cheque_date), "2026-02-04")
			self.assertIn("INV-CIF-001", jv_doc.user_remark)
			self.assertIn(pi_name, jv_doc.user_remark)

			# Verify unlinked JV accounts (reference_type and reference_name must be empty)
			for acc_row in jv_doc.accounts:
				self.assertFalse(acc_row.reference_type)
				self.assertFalse(acc_row.reference_name)

			# Verify Import File for INV-CIF-001 was created
			if_name = frappe.db.get_value("Import File", {"supplier_invoice_no": "INV-CIF-001"}, "name")
			self.assertTrue(if_name)
			if_doc = frappe.get_doc("Import File", if_name)
			self.assertEqual(if_doc.import_file_number, "INV-CIF-001")
			self.assertEqual(if_doc.bl_number, "MEDUW-BL-12345")
			self.assertEqual(if_doc.no_of_containers, "2")
			self.assertEqual(if_doc.supplier_name, "JAN JAPAN")
			self.assertEqual(if_doc.supplier_invoice_no, "INV-CIF-001")
			self.assertEqual(float(if_doc.invoice_amount), 900000.0)

			# Verify summary log format
			summary_text = res["summary"]
			self.assertIn("Breakdown Summary:", summary_text)
			self.assertIn("Time Elapsed", summary_text)
			self.assertIn("Container Full Invoices", summary_text)
			self.assertIn("Journal Entries Created", summary_text)


		finally:
			if os.path.exists(file_path):
				os.remove(file_path)

	def test_roro_and_container_mkt_statement_processing(self):
		chassis_roro = "TEST-RORO-CHASSIS-003"
		item_code_roro = "HONDA - TEST-RORO-CHASSIS-003"
		create_test_item(item_code_roro, chassis_roro)

		file_path = os.path.abspath("test_roro_statement.xlsx")
		wb = openpyxl.Workbook()
		ws = wb.active

		# Table 0: Header Mapping
		ws.append(["Sr#", "Invoice Date", "Invoice No.", "BL/SW", "SUR", "Week"])
		ws.append([1, "10-02-2026", "INV-RORO-003", "RORO-BL-88888", "N", "WK6-26"])
		ws.append([])

		# RORO Full Invoice Value
		ws.append(["RORO Full Invoice Value - ANNEXURE TO MARKET STATMENT"])
		ws.append(["Container No.", "THC", "Forwarding", "Freight", "Inspection", "JPN Expense", "Repair Cost", "Car Expense", "Vanning", "Transportation", "Freight & Other", "Cars", "Car Value", "Cont. Other Value", "Cont. Price", "Total", "Invoice No."])
		ws.append(["", 3000, 4000, 10000, 1500, 0, 0, 0, 0, 0, 0, 1, 350000, 0, 368500, 368500, "INV-RORO-003"])
		ws.append([])

		# RORO Cars
		ws.append(["RORO Cars - ANNEXURE TO MARKET STATMENT"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice No.", "Invoice Date"])
		ws.append([1, "888001", chassis_roro, 350000, "INV-RORO-003", "10-02-2026"])

		wb.save(file_path)

		try:
			invoice_info, container_rows, car_rows = parse_mkt_statement_excel(file_path)

			# Assert RORO container_no set to "RORO"
			self.assertEqual(len(car_rows), 1)
			self.assertEqual(car_rows[0]["container_no"], "RORO")
			self.assertTrue(car_rows[0]["is_roro"])

			res = process_mkt_statement(file_path, create_ifcv=False)
			self.assertTrue(res["created_pi"] + res["updated_pi"] >= 1)

			# Verify Item container_no is "RORO"
			cont_roro = frappe.db.get_value("Item", item_code_roro, "custom_container_no")
			self.assertEqual(cont_roro, "RORO")

			# Verify Purchase Invoice created with empty taxes
			pi_name = frappe.db.get_value("Purchase Invoice", {"bill_no": "INV-RORO-003"}, "name")
			self.assertTrue(pi_name)
			pi_doc = frappe.get_doc("Purchase Invoice", pi_name)
			self.assertEqual(len(pi_doc.taxes), 0)

			# Verify Journal Entry created for RORO charges
			jv_name = frappe.db.get_value("Journal Entry", {"cheque_no": "INV-RORO-003"}, "name")
			self.assertTrue(jv_name)

		finally:
			if os.path.exists(file_path):
				os.remove(file_path)

	def test_company_tax_account_resolution(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer import get_tax_expense_account, get_company_expense_account

		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
		default_acc = get_company_expense_account(company)

		comp_doc = frappe.get_doc("Company", company)
		if hasattr(comp_doc, "custom_tax_expense_accounts"):
			comp_doc.custom_tax_expense_accounts = []
			comp_doc.append("custom_tax_expense_accounts", {
				"tax_name": "TestTax",
				"account": default_acc,
				"account_currency": "JPY",
			})
			comp_doc.save(ignore_permissions=True)

			matched_acc = get_tax_expense_account(company, "TestTax", "JPY")
			self.assertEqual(matched_acc, default_acc)

			fallback_acc = get_tax_expense_account(company, "Unmapped Charge", "JPY")
			self.assertEqual(fallback_acc, default_acc)

	def test_ensure_item_color_formatting(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer import ensure_item_color

		color_1 = ensure_item_color("silver blue")
		self.assertEqual(color_1, "Silver Blue")
		self.assertTrue(frappe.db.exists("Item Color", "Silver Blue"))

		color_2 = ensure_item_color("DARK GREY")
		self.assertEqual(color_2, "Dark Grey")
		self.assertTrue(frappe.db.exists("Item Color", "Dark Grey"))

	def test_export_errored_rows(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer import download_errored_rows


		importer = frappe.new_doc("Item Excel Importer")
		importer.import_type = "Mukechi"
		failed = [
			{"row": 2, "data": {"MAKER": "TOYOTA", "CHASSIS NO": "NZE151-999", "PRICE": 500000}, "error": "Missing Maker"},
			{"chassis_no": "SH5-888", "invoice_no": "INV-888", "error": "Item not found"}
		]
		importer.failed_records = json.dumps(failed)
		importer.flags.ignore_mandatory = True
		importer.insert(ignore_permissions=True)

		download_errored_rows(importer.name)

		self.assertEqual(frappe.response["filename"], f"Errored_Rows_{importer.name}.xlsx")
		self.assertEqual(frappe.response["type"], "binary")
		self.assertTrue(len(frappe.response["filecontent"]) > 1000)


	def test_supplier_account_resolution(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer import get_supplier_payable_account

		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value("Global Defaults", "default_company")
		supplier = ensure_supplier("JAN JAPAN")

		# Test resolving account when Supplier child table has accounts
		supplier_doc = frappe.get_doc("Supplier", supplier)
		payable_acc = get_supplier_payable_account(supplier, company, "JPY")
		self.assertTrue(payable_acc)

		# Add explicit account to Supplier child table and test match
		supplier_doc.accounts = []
		supplier_doc.append("accounts", {
			"company": company,
			"account": payable_acc,
		})
		supplier_doc.save(ignore_permissions=True)

		matched = get_supplier_payable_account(supplier, company, "JPY")
		self.assertEqual(matched, payable_acc)

	def test_auto_detect_and_auto_submit(self):
		file_path = os.path.abspath(frappe.get_site_path("public", "files", "test_auto_detect.xlsx"))
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.append(["Sr#", "Invoice Date", "Invoice No.", "BL/SW", "SUR", "Week"])
		ws.append([1, "04-02-2026", "INV-TEST-003", "BL-TEST-999", "N", "WK6-26"])
		ws.append([])
		ws.append(["Full Invoice Value - ANNEXURE TO MARKET STATMENT"])
		ws.append(["Container No.", "THC", "Forwarding", "Freight", "Inspection", "JPN Expense", "Repair Cost", "Car Expense", "Vanning", "Transportation", "Freight & Other", "Cars", "Car Value", "Cont. Other Value", "Cont. Price", "Total", "Invoice No."])
		ws.append(["CONT999", 1000, 2000, 3000, 500, 0, 0, 0, 1000, 0, 0, 1, 100000, 0, 107500, 107500, "INV-TEST-003"])
		ws.append([])
		ws.append(["Invoice Cars - ANNEXURE TO MARKET STATMENT"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice No.", "Invoice Date"])
		ws.append([1, "777001", "AUTO-SUBMIT-CHASSIS-1", 100000, "INV-TEST-003", "04-02-2026"])
		wb.save(file_path)

		create_test_item("TOYOTA - AUTO-SUBMIT-CHASSIS-1", "AUTO-SUBMIT-CHASSIS-1")

		try:
			# Attach file to new Item Excel Importer doc
			importer = frappe.new_doc("Item Excel Importer")
			importer.excel_file = "/files/test_auto_detect.xlsx"
			importer.auto_submit_purchase_invoice = 1
			importer.auto_submit_journal_entry = 1
			importer.flags.ignore_mandatory = True
			importer.insert(ignore_permissions=True)

			self.assertEqual(importer.import_type, "MKT Statement")


			# Run import with auto submit options enabled
			res = process_mkt_statement(
				file_path,
				create_ifcv=False,
				auto_submit_pi=True,
				auto_submit_jv=True,
			)

			pi_name = frappe.db.get_value("Purchase Invoice", {"bill_no": "INV-TEST-003"}, "name")
			self.assertTrue(pi_name)
			pi_doc = frappe.get_doc("Purchase Invoice", pi_name)
			self.assertEqual(pi_doc.docstatus, 1)

			jv_name = frappe.db.get_value("Journal Entry", {"cheque_no": "INV-TEST-003"}, "name")
			self.assertTrue(jv_name)
			jv_doc = frappe.get_doc("Journal Entry", jv_name)
			self.assertEqual(jv_doc.docstatus, 1)

		finally:
			if os.path.exists(file_path):
				os.remove(file_path)

	def test_import_file_number_formatting_options(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer import compute_import_file_number

		# 1. Invoice No (default)
		self.assertEqual(compute_import_file_number("INV-100", "BL-200", "Invoice No"), "INV-100")
		self.assertEqual(compute_import_file_number("INV-100", "", "Invoice No"), "INV-100")

		# 2. BL Number
		self.assertEqual(compute_import_file_number("INV-100", "BL-200", "BL Number"), "BL-200")
		self.assertEqual(compute_import_file_number("INV-100", "", "BL Number"), "INV-100")  # fallback when no BL

		# 3. Invoice No - BL Number
		self.assertEqual(compute_import_file_number("INV-100", "BL-200", "Invoice No - BL Number"), "INV-100 - BL-200")
		self.assertEqual(compute_import_file_number("INV-100", "", "Invoice No - BL Number"), "INV-100")  # fallback when no BL

	def test_mkt_statement_import_file_custom_format(self):
		chassis_fmt = "TEST-FMT-CHASSIS-001"
		item_code_fmt = "TOYOTA - TEST-FMT-CHASSIS-001"
		create_test_item(item_code_fmt, chassis_fmt)

		file_path = os.path.abspath("test_fmt_statement.xlsx")
		wb = openpyxl.Workbook()
		ws = wb.active
		ws.append(["Sr#", "Invoice Date", "Invoice No.", "BL/SW", "SUR", "Week"])
		ws.append([1, "04-02-2026", "INV-FMT-001", "BL-FMT-888", "N", "WK6-26"])
		ws.append([])
		ws.append(["Full Invoice Value - ANNEXURE TO MARKET STATMENT"])
		ws.append(["Container No.", "THC", "Forwarding", "Freight", "Inspection", "JPN Expense", "Repair Cost", "Car Expense", "Vanning", "Transportation", "Freight & Other", "Cars", "Car Value", "Cont. Other Value", "Cont. Price", "Total", "Invoice No."])
		ws.append(["MSDU999", 5000, 10000, 15000, 2000, 0, 0, 0, 3000, 0, 0, 1, 500000, 0, 535000, 535000, "INV-FMT-001"])
		ws.append([])
		ws.append(["Invoice Cars - ANNEXURE TO MARKET STATMENT"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice No.", "Invoice Date"])
		ws.append([1, "999001", chassis_fmt, 500000, "INV-FMT-001", "04-02-2026"])
		wb.save(file_path)

		try:
			# Test format: "Invoice No - BL Number"
			res = process_mkt_statement(file_path, create_ifcv=False, import_file_number_format="Invoice No - BL Number")
			self.assertTrue(frappe.db.exists("Import File", "INV-FMT-001 - BL-FMT-888"))
			if_doc = frappe.get_doc("Import File", "INV-FMT-001 - BL-FMT-888")
			self.assertEqual(if_doc.import_file_number, "INV-FMT-001 - BL-FMT-888")
			self.assertEqual(if_doc.bl_number, "BL-FMT-888")
			self.assertEqual(if_doc.supplier_invoice_no, "INV-FMT-001")
		finally:
			if frappe.db.exists("Import File", "INV-FMT-001 - BL-FMT-888"):
				try:
					frappe.db.delete("Import File", {"name": "INV-FMT-001 - BL-FMT-888"})
				except Exception:
					pass
			pi_name = frappe.db.get_value("Purchase Invoice", {"bill_no": "INV-FMT-001"}, "name")
			if pi_name:
				try:
					frappe.db.delete("Purchase Invoice Item", {"parent": pi_name})
					frappe.db.delete("Purchase Invoice", {"name": pi_name})
				except Exception:
					pass
			jv_name = frappe.db.get_value("Journal Entry", {"cheque_no": "INV-FMT-001"}, "name")
			if jv_name:
				try:
					frappe.db.delete("Journal Entry Account", {"parent": jv_name})
					frappe.db.delete("Journal Entry", {"name": jv_name})
				except Exception:
					pass
			if os.path.exists(file_path):
				os.remove(file_path)


def run_test():
	t = TestItemExcelImporter()
	t.setUp()
	t.test_cif_mkt_statement_processing()
	t.setUp()
	t.test_roro_and_container_mkt_statement_processing()
	t.setUp()
	t.test_company_tax_account_resolution()
	t.setUp()
	t.test_ensure_item_color_formatting()
	t.setUp()
	t.test_export_errored_rows()
	t.setUp()
	t.test_supplier_account_resolution()
	t.setUp()
	t.test_auto_detect_and_auto_submit()
	t.setUp()
	t.test_import_file_number_formatting_options()
	t.setUp()
	t.test_mkt_statement_import_file_custom_format()
	print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
	unittest.main()


