# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import unittest
import os
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


class TestItemExcelImporter(FrappeTestCase):
	def setUp(self):
		frappe.db.rollback()
		frappe.clear_cache()
		# Cancel and delete any existing test Purchase Invoices from prior runs
		for bill_no in ("INV-CIF-001", "INV-FOB-002", "INV-TEST-003"):
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
		# Create existing test vehicle items
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

		# Table 1: Full Invoice Value (2 containers for INV-CIF-001: 1 car in cont 1, 1 car in cont 2)
		ws.append(["Full Invoice Value - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Container No.", "THC", "Forwarding", "Freight", "Inspection", "JPN Expense", "Repair Cost", "Car Expense", "Vanning", "Transportation", "Freight & Other", "Cars", "Car Value", "Cont. Other Value", "Cont. Price", "Total", "Invoice No."])
		ws.append(["MSDU1112223", 5000, 10000, 15000, 2000, 0, 0, 0, 3000, 0, 0, 1, 500000, 0, 535000, 535000, "INV-CIF-001"])
		ws.append(["MSDU4445556", 6000, 12000, 18000, 1000, 0, 0, 0, 4000, 0, 0, 1, 400000, 0, 441000, 441000, "INV-CIF-001"])
		ws.append([])

		# Table 2: Invoice Cars (INV-CIF-001 has 2 existing chassis; INV-CIF-002 has 1 non-existing chassis)
		ws.append(["Invoice Cars - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice No.", "Invoice Date"])
		ws.append([1, "999001", chassis_1, 500000, "INV-CIF-001", "04-02-2026"])
		ws.append([2, "999002", chassis_2, 400000, "INV-CIF-001", "04-02-2026"])
		ws.append([3, "999003", "MISSING-CHASSIS-999", 300000, "INV-CIF-002", "04-02-2026"])

		wb.save(file_path)

		try:
			self.assertEqual(detect_excel_format(file_path), "MKT Statement")

			res = process_mkt_statement(file_path, create_lcv=False)
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


			# Verify missing car item was NOT created in database
			self.assertFalse(frappe.db.exists("Item", "CAR-MISSING-CHASSIS-999"))
			self.assertFalse(frappe.db.exists("Item", "MISSING-CHASSIS-999"))

			# Verify Purchase Invoice for INV-CIF-001 was created
			pi_name = frappe.db.get_value("Purchase Invoice", {"bill_no": "INV-CIF-001"}, "name")
			self.assertTrue(pi_name)
			pi_doc = frappe.get_doc("Purchase Invoice", pi_name)
			self.assertEqual(pi_doc.custom_bl_sw, "MEDUW-BL-12345")

			# Verify Purchase Invoice for INV-CIF-002 was NOT created
			pi_name_2 = frappe.db.get_value("Purchase Invoice", {"bill_no": "INV-CIF-002"}, "name")
			self.assertFalse(pi_name_2)

			# Verify log contains section header and reason for INV-CIF-002
			log_text = "\n".join(res["log"])
			self.assertIn("--- Purchase Invoices Created / Updated ---", log_text)
			self.assertIn("--- Purchase Invoices Not Created ---", log_text)
			self.assertIn("Purchase Invoice not created for Supplier Invoice No: INV-CIF-002. Reason: Item not found in database for Chassis No(s): 'MISSING-CHASSIS-999'", log_text)

			# Items should contain ONLY the 2 valid car items
			self.assertEqual(len(pi_doc.items), 2)
			self.assertEqual(pi_doc.items[0].item_code, item_code_1)
			self.assertEqual(pi_doc.items[0].custom_container_no, "MSDU1112223")
			item_bl = pi_doc.items[0].get("custom_blsw") or pi_doc.items[0].get("blsw") or pi_doc.items[0].get("custom_bl")
			self.assertEqual(item_bl, "MEDUW-BL-12345")


			item_bl_2 = pi_doc.items[1].get("custom_blsw") or pi_doc.items[1].get("blsw") or pi_doc.items[1].get("custom_bl")
			self.assertEqual(item_bl_2, "MEDUW-BL-12345")


			# Taxes table should contain the total expense charges across both containers
			self.assertTrue(len(pi_doc.taxes) > 0)
			tax_dict = {t.description: float(t.tax_amount) for t in pi_doc.taxes}
			self.assertEqual(tax_dict.get("THC"), 11000.0)
			self.assertEqual(tax_dict.get("Forwarding"), 22000.0)
			self.assertEqual(tax_dict.get("Freight"), 33000.0)
			self.assertEqual(tax_dict.get("Inspection"), 3000.0)
			self.assertEqual(tax_dict.get("Vanning"), 7000.0)

			# Verify container breakdown table on PI
			self.assertEqual(len(pi_doc.custom_container_breakdown), 2)

		finally:
			if os.path.exists(file_path):
				os.remove(file_path)

	def test_fob_mkt_statement_processing(self):
		test_chassis = "TEST-FOB-CHASSIS-002"
		test_item_code = "NISSAN - TEST-FOB-CHASSIS-002"
		create_test_item(test_item_code, test_chassis)

		file_path = os.path.abspath("test_fob_statement.xlsx")
		wb = openpyxl.Workbook()
		ws = wb.active

		# Table 0
		ws.append(["Sr#", "Invoice Date", "Invoice No.", "BL/SW", "SUR", "Week"])
		ws.append([1, "05-02-2026", "INV-FOB-002", "MEDUW-BL-67890", "N", "WK6-26"])
		ws.append([])

		# Table 1
		ws.append(["Full Invoice Value - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Container No.", "THC", "Forwarding", "Freight", "Inspection", "JPN Expense", "Repair Cost", "Car Expense", "Vanning", "Transportation", "Freight & Other", "Cars", "Car Value", "Cont. Other Value", "Cont. Price", "Total", "Invoice No."])
		ws.append(["MSDU3334445", 8000, 12000, 20000, 0, 0, 0, 0, 0, 0, 0, 1, 600000, 0, 640000, 640000, "INV-FOB-002"])
		ws.append([])

		# Table 2
		ws.append(["Invoice Cars - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice No.", "Invoice Date"])
		ws.append([1, "999003", test_chassis, 600000, "INV-FOB-002", "05-02-2026"])

		wb.save(file_path)

		try:
			res = process_mkt_statement(file_path, create_lcv=True)
			self.assertTrue(res["created_pi"] + res["updated_pi"] >= 1)
			self.assertTrue(res["created_lcv"] >= 1)


			pi_name = frappe.db.get_value("Purchase Invoice", {"bill_no": "INV-FOB-002"}, "name")
			self.assertTrue(pi_name)
			pi_doc = frappe.get_doc("Purchase Invoice", pi_name)
			self.assertEqual(pi_doc.custom_bl_sw, "MEDUW-BL-67890")

			# Taxes are always added to Purchase Invoice (no more FOB/CIF split)
			self.assertTrue(len(pi_doc.taxes) > 0)

			# Landed Cost Voucher created for PI
			lcv_name = frappe.db.get_value("Landed Cost Purchase Receipt", {"receipt_document": pi_name}, "parent")
			self.assertTrue(lcv_name)
			lcv = frappe.get_doc("Landed Cost Voucher", lcv_name)
			self.assertTrue(len(lcv.taxes) > 0)

		finally:
			if os.path.exists(file_path):
				os.remove(file_path)

	def test_ignore_subsequent_tables_in_mkt_statement(self):
		file_path = os.path.abspath("test_subsequent_tables_statement.xlsx")
		wb = openpyxl.Workbook()
		ws = wb.active

		# Table 0: Header Info
		ws.append(["Sr#", "Invoice Date", "Invoice No.", "BL/SW", "SUR", "Week"])
		ws.append([1, "04-02-2026", "INV-TEST-003", "MEDUW-BL-99999", "N", "WK6-26"])
		ws.append([])

		# Table 1: Full Invoice Value
		ws.append(["Full Invoice Value - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Container No.", "THC", "Forwarding", "Freight", "Inspection", "JPN Expense", "Repair Cost", "Car Expense", "Vanning", "Transportation", "Freight & Other", "Cars", "Car Value", "Cont. Other Value", "Cont. Price", "Total", "Invoice No."])
		ws.append(["MSDU7778889", 5000, 10000, 15000, 2000, 0, 0, 0, 3000, 0, 0, 1, 500000, 0, 535000, 535000, "INV-TEST-003"])
		ws.append([])

		# Table 2: Invoice Cars
		ws.append(["Invoice Cars - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 09-07-2026 )"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice No.", "Invoice Date"])
		ws.append([1, "999101", "VALID-CHASSIS-001", 500000, "INV-TEST-003", "04-02-2026"])
		ws.append([])

		# Table 3: Container Price (subsequent table)
		ws.append(["Container Price - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 28-07-2026 )"])
		ws.append(["Sr#", "Description", "Container Price", "Invoice No.", "Invoice Date", "Container No."])
		ws.append([1, "Test Container Price", 100000, "INV-TEST-003", "04-02-2026", "MSDU7778889"])
		ws.append([])

		# Table 4: RORO Cars (subsequent table)
		ws.append(["RORO Cars - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 28-07-2026 )"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Invoice Date", "Invoice No."])
		ws.append([1, "999201", "RORO-CHASSIS-999", 400000, "13-06-2026", "T.TAN001/26RO MOL"])
		ws.append([])

		# Table 5: Not Invoiced Cars (subsequent table)
		ws.append(["Not Invoiced Cars - ANNEXURE TO MARKET STATMENT ( 01-02-2026 - 28-07-2026 )"])
		ws.append(["Sr#", "Stock ID", "Chassis No.", "Car Price", "Purchase Date"])
		ws.append([1, "999301", "NOT-INV-CHASSIS-888", 300000, "15-06-2026"])

		wb.save(file_path)

		try:
			invoice_info, container_rows, car_rows = parse_mkt_statement_excel(file_path)

			# Verify that ONLY the car from Invoice Cars table was extracted
			chassis_list = [c["chassis_no"] for c in car_rows]
			self.assertIn("VALID-CHASSIS-001", chassis_list)
			self.assertNotIn("RORO-CHASSIS-999", chassis_list)
			self.assertNotIn("NOT-INV-CHASSIS-888", chassis_list)
			self.assertEqual(len(car_rows), 1)

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


def run_test():
	t = TestItemExcelImporter()
	t.setUp()
	t.test_cif_mkt_statement_processing()
	t.setUp()
	t.test_fob_mkt_statement_processing()
	t.setUp()
	t.test_ignore_subsequent_tables_in_mkt_statement()
	t.setUp()
	t.test_company_tax_account_resolution()
	t.setUp()
	t.test_ensure_item_color_formatting()
	print("ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
	unittest.main()
