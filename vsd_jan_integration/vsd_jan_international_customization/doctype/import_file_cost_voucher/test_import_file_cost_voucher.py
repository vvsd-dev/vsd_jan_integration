# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Unit tests for multi-IFCV expense reuse and BL-wide distribution helpers."""

import unittest
from unittest.mock import patch

from frappe.utils import flt


class TestExpenseReuseHelpers(unittest.TestCase):
	def test_oneshot_vs_bl_wide(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
			is_bl_wide_distribution,
			is_oneshot_distribution,
		)

		self.assertTrue(is_oneshot_distribution("By Vehicle Manual", "By Vehicle"))
		self.assertTrue(is_oneshot_distribution(None, "By Vehicle"))
		self.assertFalse(is_oneshot_distribution("By BL Equal", "By BL Equal"))
		self.assertFalse(is_oneshot_distribution("By Formula", "By Formula"))

		self.assertTrue(is_bl_wide_distribution("By BL Equal", "By BL Equal"))
		self.assertTrue(is_bl_wide_distribution("By BL M3", "By BL M3"))
		self.assertTrue(is_bl_wide_distribution("By Formula", "By Formula"))
		self.assertTrue(is_bl_wide_distribution(None, "By BL"))
		self.assertFalse(is_bl_wide_distribution("By Vehicle Manual", "By Vehicle"))

	def test_consumption_key(self):
		from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
			expense_consumption_key,
		)

		self.assertEqual(
			expense_consumption_key("JE-1", "Acc-A", "ITEM-1", "tra_duty"),
			("JE-1", "Acc-A", "ITEM-1", "tra_duty"),
		)
		self.assertEqual(
			expense_consumption_key(" JE-1 ", " Acc-A ", None, None),
			("JE-1", "Acc-A", "", ""),
		)


class TestBlWideShareMath(unittest.TestCase):
	"""Pure share math: 1 of 7 cars must get 1/7 of a BL Equal expense."""

	def test_equal_share_one_of_seven(self):
		bl_count = 7
		exp_amount = 700_000
		share = flt(exp_amount) / bl_count
		self.assertAlmostEqual(share, 100_000.0, places=4)

	def test_m3_share_partial_ifcv(self):
		bl_m3 = [10, 20, 30]  # total 60
		exp_amount = 60_000
		# IFCV only has first car
		share = flt(exp_amount) * (10 / sum(bl_m3))
		self.assertAlmostEqual(share, 10_000.0, places=4)


class TestDistributePartialBl(unittest.TestCase):
	"""Exercise _distribute_allocations with mocked BL vehicle set."""

	def test_bl_equal_uses_full_bl_denominator(self):
		from frappe import _dict
		from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher import (
			import_file_cost_voucher as mod,
		)

		# Lightweight stand-in — avoid Document/meta (needs frappe.init)
		doc = _dict(
			import_file="IF-N039",
			name="IFCV-DRAFT-1",
			expenses=[],
			allocations=[],
			vehicles=[],
		)
		doc._vehicle_rows = lambda: [
			_dict(name="CAR-A", custom_m3=10, custom_chassis_no="CH-A")
		]
		doc._bl_vehicle_rows = lambda: [
			_dict(name=f"CAR-{c}", custom_m3=10, custom_chassis_no=f"CH-{c}")
			for c in "ABCDEFG"
		]
		doc._allocation_dict = lambda item_name, exp, amount, chassis_no=None: {
			"item": item_name,
			"chassis_no": chassis_no,
			"costing_head": exp.costing_head,
			"account": exp.expense_account,
			"currency": exp.currency,
			"amount": flt(amount),
			"source_row": exp.idx,
		}
		captured = []

		def _set(table, rows):
			doc[table] = rows

		def _append(table, row):
			if table == "allocations":
				captured.append(row)

		doc.set = _set
		doc.append = _append

		exp = _dict(
			amount=700_000,
			distribution_method="By BL Equal",
			costing_head="clearing_container",
			expense_account="Clearing - JIL",
			currency="TZS",
			source="JE-BL-CLEAR",
			linked_item=None,
			description="clearing",
			remarks="",
			idx=1,
		)
		doc.expenses = [exp]

		with patch.object(mod, "get_bl_allocated_items", return_value=set()):
			mod.ImportFileCostVoucher._distribute_allocations(doc, keep_manual=False)

		self.assertEqual(len(captured), 1)
		self.assertEqual(captured[0]["item"], "CAR-A")
		self.assertAlmostEqual(flt(captured[0]["amount"]), 100_000.0, places=2)


if __name__ == "__main__":
	unittest.main()
