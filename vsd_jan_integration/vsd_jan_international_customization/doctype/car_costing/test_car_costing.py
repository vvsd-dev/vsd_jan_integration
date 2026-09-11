# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from vsd_jan_integration.patches.seed_costing_heads import execute as seed_heads
from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
	load_template_lines,
	recalculate_car_costing,
)


class TestCarCostingRevamp(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		seed_heads()

	def test_projected_calculation(self):
		item_code = "TEST-REVAMP-COST-001"
		if not frappe.db.exists("Item", item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item_code,
					"item_group": "Products",
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"custom_chassis_no": "TESTCHASSIS-REV-1",
					"custom_maker": "TOYOTA",
					"custom_price": 217000,
				}
			).insert(ignore_permissions=True)

		doc = frappe.get_doc(
			{
				"doctype": "Car Costing",
				"item": item_code,
				"import_file": frappe.db.get_value("Import File", {}, "name") or self._make_import_file(),
				"exchange_rate": 2700,
				"yen_exchange_rate": 155,
				"tz_costing_lines": load_template_lines("Tanzania"),
				"japan_costing_lines": load_template_lines("Japan"),
			}
		)

		for row in doc.tz_costing_lines:
			if row.costing_code == "tra_duty":
				row.projected_amount = 9600000
			elif row.costing_code == "tpa":
				row.projected_amount = 141176
			elif row.costing_code == "repairing_charges_local":
				row.projected_amount = 0
			elif row.costing_code == "fuel_port_to_yard":
				row.projected_amount = 35000

		for row in doc.japan_costing_lines:
			if row.costing_code == "icd":
				row.projected_amount = 191.529
			elif row.costing_code == "shipping_line":
				row.projected_amount = 1384.902

		recalculate_car_costing(doc)
		self.assertGreater(flt(doc.total_exp_tsh), 0)
		self.assertGreater(flt(doc.total_exp_usd), 0)
		self.assertGreater(flt(doc.total_cost_usd), 0)
		self.assertGreater(flt(doc.cost), 0)
		self.assertEqual(flt(doc.price), flt(doc.cost))

	def test_load_from_item_no_crash(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing import (
			load_from_item,
		)

		item_code = "TEST-REVAMP-COST-002"
		if not frappe.db.exists("Item", item_code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": item_code,
					"item_group": "Products",
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"custom_chassis_no": "TESTCHASSIS-REV-2",
					"custom_maker": "HONDA",
					"custom_price": 100000,
				}
			).insert(ignore_permissions=True)

		name = load_from_item(item=item_code)
		doc = frappe.get_doc("Car Costing", name)
		self.assertTrue(doc.tz_costing_lines)
		self.assertEqual(flt(doc.price), flt(doc.cost))

	def _make_import_file(self):
		name = "TEST-IMPORT-FILE-001"
		if not frappe.db.exists("Import File", name):
			# Import File required fields vary by site; try minimal
			doc = frappe.new_doc("Import File")
			if hasattr(doc, "import_file_number"):
				doc.import_file_number = name
			doc.bl_number = "TEST-BL-001"
			doc.insert(ignore_permissions=True)
			return doc.name
		return name

	def tearDown(self):
		frappe.db.rollback()
