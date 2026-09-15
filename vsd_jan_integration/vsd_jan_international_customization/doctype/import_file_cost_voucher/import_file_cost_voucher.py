# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ImportFileCostVoucher(Document):
	def validate(self):
		self._sync_expense_distribution_from_costing()
		self._distribute_allocations()
		self._update_vehicle_purchase_and_charges()
		self.total_expense_amount = sum(flt(r.amount) for r in (self.expenses or []))
		self.total_allocated_amount = sum(flt(r.amount) for r in (self.allocations or []))

	def on_submit(self):
		# Always write Actuals onto Item costing lines (Car Costing = Expected only; independent)
		self.push_actual_to_item()
		self.update_stock_valuation_from_allocations()

	def update_stock_valuation_from_allocations(self):
		"""Create/submit Landed Cost Voucher(s) from IFCV allocations (LCV-style valuation).

		Valuation = PI purchase base + allocated IFCV charges, via ERPNext LCV submit.
		Also refreshes Item.custom_cost from PI rate + actual totals (no selling price).

		Allocation amounts are in account currency; LCV / stock valuation use company currency.
		"""
		from collections import defaultdict

		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		posting_date = self.posting_date or frappe.utils.today()

		by_item_total = defaultdict(float)
		by_item_by_account = defaultdict(lambda: defaultdict(float))
		for a in self.allocations or []:
			if not a.item or not flt(a.amount):
				continue
			acc = a.account or frappe.db.get_value("Costing", a.costing_head, "account")
			cur = a.currency or (
				frappe.db.get_value("Account", acc, "account_currency") if acc else None
			)
			base_amt = _amount_in_company_currency(flt(a.amount), cur, company, posting_date)
			by_item_total[a.item] += base_amt
			if acc:
				by_item_by_account[a.item][acc] += base_amt

		if not by_item_total:
			return

		# Resolve stock PI line per item
		pi_groups = defaultdict(lambda: {"items": {}, "company": None, "grand_total": 0, "supplier": None, "posting_date": None})
		for item_code, total in by_item_total.items():
			row = frappe.db.sql(
				"""
				SELECT
					pi.name as pi_name,
					pii.name as pii_name,
					pii.qty,
					pii.rate,
					pii.amount,
					pii.base_rate,
					pii.base_amount,
					pii.cost_center,
					pii.description,
					pi.company,
					pi.supplier,
					pi.posting_date,
					pi.grand_total,
					pi.base_grand_total
				FROM `tabPurchase Invoice` pi
				INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
				WHERE pii.item_code = %s
					AND pi.docstatus = 1
					AND pi.update_stock = 1
				ORDER BY pi.posting_date DESC, pi.creation DESC
				LIMIT 1
				""",
				item_code,
				as_dict=True,
			)
			if not row:
				continue
			r = row[0]
			g = pi_groups[r.pi_name]
			g["company"] = r.company
			g["supplier"] = r.supplier
			g["posting_date"] = r.posting_date
			g["grand_total"] = flt(r.base_grand_total) or flt(r.grand_total)
			g["items"][item_code] = r

		created = []
		for pi_name, group in pi_groups.items():
			try:
				lcv_name = self._create_and_submit_lcv_for_pi(
					pi_name,
					group,
					{item: by_item_by_account[item] for item in group["items"]},
					{item: by_item_total[item] for item in group["items"]},
				)
				if lcv_name:
					created.append(lcv_name)
			except Exception:
				frappe.log_error(
					title=f"IFCV LCV valuation for {pi_name}",
					message=frappe.get_traceback(),
				)

		# Sync Item.custom_cost ≈ purchase base + actuals (display); never selling price
		for item_code, total_actual in by_item_total.items():
			try:
				pi_row = None
				for g in pi_groups.values():
					if item_code in g["items"]:
						pi_row = g["items"][item_code]
						break
				base = flt(pi_row.base_amount) if pi_row else 0
				if not base and pi_row:
					base = flt(pi_row.amount)
				# If no PI, fall back to purchase price field if present
				if not base:
					base = flt(frappe.db.get_value("Item", item_code, "custom_price"))
				frappe.db.set_value(
					"Item",
					item_code,
					"custom_cost",
					base + flt(total_actual),
					update_modified=False,
				)
			except Exception:
				pass

		if created:
			self.add_comment(
				"Comment",
				_("Submitted Landed Cost Voucher(s) for valuation: {0}").format(", ".join(created)),
			)

	def _create_and_submit_lcv_for_pi(self, pi_name, group, item_account_map, item_total_map):
		"""Build LCV from IFCV — mirrors manual MAT-LCV pattern, ERPNext-safe.

		ERPNext allows only ONE tax row when Distribute Manually. Strategy:
		- One LCV with Distribute Manually
		- One tax row = sum of applicable charges (company currency)
		- Item.applicable_charges = vehicle/IFCV allocation totals (already computed)

		Per-account JE expenses stay on the books; LCV reclasses the combined charge
		into stock valuation. Stock In Hand is never included (filtered upstream).
		"""
		from erpnext.controllers.taxes_and_totals import init_landed_taxes_and_totals

		company = group["company"]
		cost_center = frappe.db.get_value("Company", company, "cost_center") or frappe.db.get_value(
			"Cost Center", {"company": company, "is_group": 0}, "name"
		)

		# Prefer vehicle.applicable_charges when present (set on save)
		charges_by_item = {}
		for v in self.vehicles or []:
			if v.item and v.item in group["items"] and flt(v.applicable_charges):
				charges_by_item[v.item] = flt(v.applicable_charges)
		if not charges_by_item:
			charges_by_item = {k: flt(v) for k, v in (item_total_map or {}).items() if flt(v)}

		tax_total = sum(charges_by_item.values())
		if not tax_total:
			return None

		desc = f"IFCV {self.name} — applicable charges"
		existing = frappe.db.sql(
			"""
			SELECT lcv.name
			FROM `tabLanded Cost Voucher` lcv
			INNER JOIN `tabLanded Cost Purchase Receipt` lpr ON lpr.parent = lcv.name
			INNER JOIN `tabLanded Cost Taxes and Charges` lct ON lct.parent = lcv.name
			WHERE lpr.receipt_document = %s
				AND lcv.docstatus = 1
				AND lct.description = %s
			LIMIT 1
			""",
			(pi_name, desc),
		)
		if existing:
			return existing[0][0]

		# Pick expense account: prefer first allocated Costing account (non-stock)
		expense_account = None
		for item_code, acc_map in (item_account_map or {}).items():
			for acc in acc_map:
				if acc and not _is_stock_in_hand_account(acc):
					expense_account = acc
					break
			if expense_account:
				break
		if not expense_account:
			expense_account = frappe.db.get_value(
				"Company", company, "expenses_included_in_valuation"
			) or frappe.db.get_value(
				"Account",
				{"company": company, "account_type": "Expense Account", "is_group": 0},
				"name",
			)
		if not expense_account:
			frappe.throw(_("No expense account available for Landed Cost Voucher from IFCV"))

		lcv = frappe.new_doc("Landed Cost Voucher")
		lcv.company = company
		lcv.posting_date = self.posting_date or frappe.utils.today()
		lcv.distribute_charges_based_on = "Distribute Manually"

		lcv.append(
			"purchase_receipts",
			{
				"receipt_document_type": "Purchase Invoice",
				"receipt_document": pi_name,
				"supplier": group.get("supplier")
				or frappe.db.get_value("Purchase Invoice", pi_name, "supplier"),
				"posting_date": group.get("posting_date")
				or frappe.db.get_value("Purchase Invoice", pi_name, "posting_date"),
				"grand_total": group["grand_total"],
			},
		)

		lcv.append(
			"taxes",
			{
				"expense_account": expense_account,
				"description": desc,
				"amount": tax_total,
			},
		)

		for item_code, r in group["items"].items():
			charge = flt(charges_by_item.get(item_code))
			if not charge:
				continue
			lcv.append(
				"items",
				{
					"receipt_document_type": "Purchase Invoice",
					"receipt_document": pi_name,
					"purchase_receipt_item": r.pii_name,
					"item_code": item_code,
					"description": r.description or item_code,
					"qty": flt(r.qty) or 1,
					"rate": flt(r.base_rate) or flt(r.rate),
					"amount": flt(r.base_amount) or flt(r.amount),
					"cost_center": r.cost_center or cost_center,
					"applicable_charges": charge,
				},
			)

		if not lcv.items:
			return None

		items_total = sum(flt(i.applicable_charges) for i in lcv.items)
		diff = flt(tax_total) - flt(items_total)
		if lcv.items and abs(diff) >= 0.0001:
			lcv.items[-1].applicable_charges = flt(lcv.items[-1].applicable_charges) + diff

		try:
			lcv.flags.ignore_permissions = True
			init_landed_taxes_and_totals(lcv)
			lcv.set_total_taxes_and_charges()
			if lcv.taxes:
				lcv.taxes[0].amount = tax_total
			lcv.set_total_taxes_and_charges()
			items_total = sum(flt(i.applicable_charges) for i in lcv.items)
			diff = flt(lcv.total_taxes_and_charges) - flt(items_total)
			if lcv.items and abs(diff) >= 0.0001:
				lcv.items[-1].applicable_charges = flt(lcv.items[-1].applicable_charges) + diff
			lcv.insert(ignore_permissions=True)
			lcv.submit()
			return lcv.name
		except Exception:
			frappe.log_error(
				title=f"IFCV LCV {self.name} / {pi_name}",
				message=frappe.get_traceback(),
			)
			return None

	def push_actual_to_item(self):
		"""Match IFCV allocations onto Item Expected/Actual costing tables.

		- If a Costing row already exists (usually from Car Costing Expected), set Actual.
		- If missing, append a new row with Actual (Expected stays 0).
		"""
		from collections import defaultdict

		from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
			refresh_item_expense_totals,
			sort_costing_lines,
		)

		by_item = defaultdict(list)
		for a in self.allocations or []:
			if not a.item or not a.costing_head:
				continue
			by_item[a.item].append(a)

		touched = []
		company = (
			frappe.defaults.get_user_default("Company")
			or frappe.db.get_single_value("Global Defaults", "default_company")
		)
		for item_code, allocs in by_item.items():
			# Sum amounts per costing head (multiple expense rows can share a head)
			amounts = defaultdict(float)
			heads = {}
			for a in allocs:
				# Allocation amounts are in account currency; Item Actual follows Costing.currency (Excel)
				target_cur = frappe.db.get_value("Costing", a.costing_head, "currency") if a.costing_head else None
				src_cur = a.currency or (
					frappe.db.get_value("Account", a.account, "account_currency") if a.account else None
				)
				amt = flt(a.amount)
				if target_cur and src_cur and target_cur != src_cur:
					base = _amount_in_company_currency(
						amt, src_cur, company, self.posting_date
					)
					amt = _amount_from_company_currency(
						base, target_cur, company, self.posting_date
					)
				amounts[a.costing_head] += amt
				heads[a.costing_head] = a

			item = frappe.get_doc("Item", item_code)
			tz_by_code = {
				(r.costing_code or r.costing_head): r for r in (item.custom_tz_costing or [])
			}
			jp_by_code = {
				(r.costing_code or r.costing_head): r for r in (item.custom_japan_costing or [])
			}

			for costing_head, amount in amounts.items():
				meta = frappe.db.get_value(
					"Costing",
					costing_head,
					["costing_code", "costing_name", "region", "entry_mode", "allocation_scope", "account", "currency"],
					as_dict=True,
				)
				if not meta:
					continue
				code = meta.costing_code or costing_head
				table_name = "custom_tz_costing" if meta.region == "Tanzania" else "custom_japan_costing"
				lookup = tz_by_code if meta.region == "Tanzania" else jp_by_code
				row = lookup.get(code) or lookup.get(costing_head)
				if row:
					row.actual_amount = amount
					if not row.costing_name:
						row.costing_name = meta.costing_name
					if not row.account:
						row.account = meta.account
					if not row.currency:
						row.currency = meta.currency
				else:
					new_row = {
						"costing_head": costing_head,
						"costing_code": code,
						"costing_name": meta.costing_name,
						"entry_mode": meta.entry_mode,
						"allocation_scope": meta.allocation_scope,
						"account": meta.account or heads[costing_head].account,
						"currency": meta.currency,
						"projected_amount": 0,
						"actual_amount": amount,
					}
					item.append(table_name, new_row)
					lookup[code] = item.get(table_name)[-1]

			item.set("custom_tz_costing", sort_costing_lines(item.custom_tz_costing))
			item.set("custom_japan_costing", sort_costing_lines(item.custom_japan_costing))
			refresh_item_expense_totals(item)
			item.flags.ignore_permissions = True
			item.save()
			touched.append(item_code)

		if touched:
			self.add_comment(
				"Comment",
				_("Updated Item Actual costs for: {0}").format(", ".join(touched)),
			)

	def _costing_meta_for_expense(self, exp):
		"""Resolve Costing allocation_scope + entry_mode for an expense line (source of truth)."""
		head = None
		if exp.costing_head and frappe.db.exists("Costing", exp.costing_head):
			head = frappe.db.get_value(
				"Costing",
				exp.costing_head,
				["name", "allocation_scope", "entry_mode", "account", "costing_code"],
				as_dict=True,
			)
		elif exp.expense_account:
			heads = frappe.get_all(
				"Costing",
				filters={"disabled": 0, "account": exp.expense_account},
				fields=["name", "allocation_scope", "entry_mode", "account", "costing_code"],
			)
			if len(heads) == 1:
				head = heads[0]
			elif heads:
				code = (getattr(exp, "costing_code", None) or "").strip()
				head = next((h for h in heads if h.costing_code == code), heads[0])
		if head:
			if not exp.costing_head:
				exp.costing_head = head.name
			if not getattr(exp, "costing_code", None) and head.costing_code:
				exp.costing_code = head.costing_code
			return head.allocation_scope, head.entry_mode
		return None, None

	def _sync_expense_distribution_from_costing(self):
		"""Always derive allocation_scope + distribution_method from Costing (no child-table defaults)."""
		for exp in self.expenses or []:
			scope, entry_mode = self._costing_meta_for_expense(exp)
			if scope is not None or entry_mode:
				if scope:
					exp.allocation_scope = scope
				exp.distribution_method = distribution_method_from_costing(scope, entry_mode)

	def _update_vehicle_purchase_and_charges(self):
		"""Fill purchase FX from submitted PI + applicable_charges from allocations (company currency).

		applicable_charges is what Landed Cost Voucher items get on Distribute Manually.
		Stock In Hand expenses are already excluded from IFCV expenses/allocations.
		"""
		from collections import defaultdict

		company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		posting_date = self.posting_date or frappe.utils.today()
		comp_cur = frappe.db.get_value("Company", company, "default_currency") if company else None

		# First pass: purchase FX from submitted stock PI
		fx_by_item = {}
		for v in self.vehicles or []:
			if not v.item:
				continue
			pi = _purchase_invoice_for_item(v.item, self.import_file)
			if pi:
				v.purchase_price = flt(pi.rate)
				v.purchase_currency = pi.currency or v.purchase_currency or "JPY"
				v.exchange_rate = flt(pi.conversion_rate) or 1.0
				v.purchase_amount_company = (
					flt(pi.base_amount)
					if flt(pi.base_amount)
					else flt(v.purchase_price) * flt(v.exchange_rate)
				)
			else:
				if not flt(v.exchange_rate):
					v.exchange_rate = 1.0
					if v.purchase_currency and comp_cur and v.purchase_currency != comp_cur:
						try:
							from erpnext.setup.utils import get_exchange_rate

							v.exchange_rate = (
								flt(
									get_exchange_rate(
										v.purchase_currency,
										comp_cur,
										posting_date,
										"for_buying",
									)
								)
								or 1.0
							)
						except Exception:
							v.exchange_rate = 1.0
				v.purchase_amount_company = flt(v.purchase_price) * flt(v.exchange_rate)

			fx_by_item[v.item] = {
				"currency": v.purchase_currency,
				"rate": flt(v.exchange_rate) or 1.0,
			}

		# Second pass: applicable charges (prefer PI FX for same currency as purchase)
		charges_by_item = defaultdict(float)
		for a in self.allocations or []:
			if not a.item or not flt(a.amount):
				continue
			acc = a.account or frappe.db.get_value("Costing", a.costing_head, "account")
			cur = a.currency or (
				frappe.db.get_value("Account", acc, "account_currency") if acc else None
			)
			fx = fx_by_item.get(a.item) or {}
			if cur and comp_cur and cur == comp_cur:
				base_amt = flt(a.amount)
			elif cur and fx.get("currency") == cur and flt(fx.get("rate")):
				base_amt = flt(a.amount) * flt(fx["rate"])
			else:
				base_amt = _amount_in_company_currency(flt(a.amount), cur, company, posting_date)
			charges_by_item[a.item] += base_amt

		for v in self.vehicles or []:
			if v.item:
				v.applicable_charges = flt(charges_by_item.get(v.item))

	def _vehicle_rows(self):
		rows = []
		for v in self.vehicles or []:
			if not v.item:
				continue
			rows.append(
				frappe._dict(
					{
						"name": v.item,
						"custom_m3": flt(v.m3),
						"custom_chassis_no": (v.chassis_no or "").strip()
						or frappe.db.get_value("Item", v.item, "custom_chassis_no"),
					}
				)
			)
		if rows:
			return rows
		return get_vehicles_for_import_file(self.import_file)

	def _allocation_dict(self, item_name, exp, amount, chassis_no=None):
		"""Build an allocation row; always set chassis_no (fetch_from does not run on append)."""
		if not chassis_no:
			chassis_no = frappe.db.get_value("Item", item_name, "custom_chassis_no")
		return {
			"item": item_name,
			"chassis_no": chassis_no,
			"costing_head": exp.costing_head,
			"account": exp.expense_account,
			"currency": exp.currency
			or (
				frappe.db.get_value("Account", exp.expense_account, "account_currency")
				if exp.expense_account
				else None
			),
			"amount": flt(amount),
			"source_row": exp.idx,
		}

	def _distribute_allocations(self, keep_manual=True):
		manual_rows = []
		if keep_manual:
			manual_rows = [
				a.as_dict()
				for a in (self.allocations or [])
				if a.source_row
				and any(
					e.idx == a.source_row and e.distribution_method == "By Vehicle Manual"
					for e in (self.expenses or [])
				)
			]
			# Drop stale manual rows whose amounts no longer match the expense
			cleaned = []
			for a in manual_rows:
				exp = next((e for e in (self.expenses or []) if e.idx == a.get("source_row")), None)
				if not exp:
					continue
				# Keep only if this source_row's allocated total still matches expense
				cleaned.append(a)
			# Re-validate totals per source_row
			from collections import defaultdict

			by_src = defaultdict(float)
			for a in cleaned:
				by_src[a.get("source_row")] += flt(a.get("amount"))
			manual_rows = [
				a
				for a in cleaned
				if abs(
					by_src[a.get("source_row")]
					- flt(next(e.amount for e in self.expenses if e.idx == a.get("source_row")))
				)
				<= 0.5
			]

		self.set("allocations", [])
		items = self._vehicle_rows()
		if not items:
			for a in manual_rows:
				if not a.get("chassis_no") and a.get("item"):
					a["chassis_no"] = frappe.db.get_value("Item", a["item"], "custom_chassis_no")
				self.append("allocations", a)
			return

		total_m3 = sum(flt(i.custom_m3) for i in items) or 0
		item_names = {i.name for i in items}
		chassis_to_item = {
			(i.custom_chassis_no or frappe.db.get_value("Item", i.name, "custom_chassis_no") or "").upper(): i.name
			for i in items
		}
		formula_expenses = []

		for exp in self.expenses or []:
			if not flt(exp.amount):
				continue
			if exp.distribution_method == "By Formula":
				# Second pass after other methods have filled line amounts (e.g. tra_duty)
				formula_expenses.append(exp)
				continue
			if exp.distribution_method == "By Vehicle Manual":
				kept = [a for a in manual_rows if a.get("source_row") == exp.idx]
				if kept:
					for a in kept:
						if not a.get("chassis_no") and a.get("item"):
							a["chassis_no"] = frappe.db.get_value("Item", a["item"], "custom_chassis_no")
						self.append("allocations", a)
					continue

				# Prefer JE.custom_item when set and on this Import File
				matched = None
				linked = getattr(exp, "linked_item", None)
				if linked and linked in item_names:
					matched = linked
				else:
					# Fallback: chassis substring in remark/title/description
					hint = f"{exp.description or ''} {exp.remarks or ''} {exp.source or ''}".upper()
					for chassis, item_name in chassis_to_item.items():
						if chassis and chassis in hint:
							matched = item_name
							break
				if matched:
					ch = next(
						(i.custom_chassis_no for i in items if i.name == matched),
						None,
					)
					self.append("allocations", self._allocation_dict(matched, exp, exp.amount, ch))
				continue

			for item in items:
				if exp.distribution_method == "By BL M3":
					amount = (flt(exp.amount) * (flt(item.custom_m3) / total_m3)) if total_m3 else 0
				else:
					amount = flt(exp.amount) / len(items)

				self.append(
					"allocations",
					self._allocation_dict(item.name, exp, amount, item.custom_chassis_no),
				)

		# Formula heads (e.g. Wharfage = TRA Duty × 7%): bulk JE at BL, split by formula
		if formula_expenses:
			self._distribute_formula_expenses(formula_expenses, items)

	def _distribute_formula_expenses(self, formula_expenses, items):
		"""Split BL-bulk Formula expenses using Costing.formula and sibling allocations.

		Example: Wharfage formula `{line.tra_duty} * 0.07` with TRA already allocated
		per car → Noah TRA 9,600,000 → Wharfage 672,000 (not equal BL share).
		"""
		from collections import defaultdict

		from vsd_jan_integration.vsd_jan_international_customization.utils.costing_engine import (
			_eval,
		)

		line_by_item = defaultdict(dict)
		for a in self.allocations or []:
			if not a.item or not a.costing_head:
				continue
			code = frappe.db.get_value("Costing", a.costing_head, "costing_code") or a.costing_head
			line_by_item[a.item][code] = line_by_item[a.item].get(code, 0) + flt(a.amount)

		for exp in formula_expenses:
			formula = None
			if exp.costing_head:
				formula = frappe.db.get_value("Costing", exp.costing_head, "formula")
			raw = {}
			for item in items:
				ctx = {"line": dict(line_by_item.get(item.name) or {})}
				try:
					raw[item.name] = flt(_eval(formula, ctx)) if formula else 0.0
				except Exception:
					raw[item.name] = 0.0
			total_raw = sum(raw.values())
			code = (
				(frappe.db.get_value("Costing", exp.costing_head, "costing_code") if exp.costing_head else None)
				or (exp.costing_head or "")
			)
			for item in items:
				if total_raw:
					amount = flt(exp.amount) * (raw[item.name] / total_raw)
				else:
					amount = flt(exp.amount) / len(items) if items else 0
				self.append(
					"allocations",
					self._allocation_dict(item.name, exp, amount, item.custom_chassis_no),
				)
				if code:
					line_by_item[item.name][code] = line_by_item[item.name].get(code, 0) + amount


def _amount_in_company_currency(amount, currency, company, date=None):
	"""Convert account-currency amount to company currency for LCV / valuation."""
	if not amount:
		return 0.0
	comp_cur = frappe.db.get_value("Company", company, "default_currency") if company else None
	if not currency or not comp_cur or currency == comp_cur:
		return flt(amount)
	try:
		from erpnext.setup.utils import get_exchange_rate

		rate = flt(get_exchange_rate(currency, comp_cur, date or frappe.utils.today(), "for_buying"))
	except Exception:
		rate = 0
	return flt(amount) * (rate or 1.0)


def _amount_from_company_currency(base_amount, currency, company, date=None):
	"""Convert company-currency amount into target currency."""
	if not base_amount:
		return 0.0
	comp_cur = frappe.db.get_value("Company", company, "default_currency") if company else None
	if not currency or not comp_cur or currency == comp_cur:
		return flt(base_amount)
	try:
		from erpnext.setup.utils import get_exchange_rate

		rate = flt(get_exchange_rate(comp_cur, currency, date or frappe.utils.today(), "for_buying"))
	except Exception:
		rate = 0
	if rate:
		return flt(base_amount) * rate
	# Inverse fallback
	try:
		from erpnext.setup.utils import get_exchange_rate

		inv = flt(get_exchange_rate(currency, comp_cur, date or frappe.utils.today(), "for_buying"))
	except Exception:
		inv = 0
	return (flt(base_amount) / inv) if inv else flt(base_amount)


def _purchase_invoice_for_item(item_code, import_file=None):
	"""Prefer submitted stock PI for this item (same Import File when set)."""
	params = [item_code]
	import_filter = ""
	if import_file and frappe.db.has_column("Purchase Invoice", "import_file"):
		import_filter = "AND pi.import_file = %s"
		params.append(import_file)

	rows = frappe.db.sql(
		f"""
		SELECT
			pi.name as pi_name,
			pi.currency,
			pi.conversion_rate,
			pi.docstatus,
			pi.update_stock,
			pii.rate,
			pii.amount,
			pii.base_rate,
			pii.base_amount
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.item_code = %s
			AND pi.docstatus = 1
			AND pi.update_stock = 1
			{import_filter}
		ORDER BY pi.posting_date DESC, pi.creation DESC
		LIMIT 1
		""",
		tuple(params),
		as_dict=True,
	)
	if rows:
		return rows[0]

	# Fallback: any submitted PI on Import File (even if not update_stock)
	if import_file and frappe.db.has_column("Purchase Invoice", "import_file"):
		rows = frappe.db.sql(
			"""
			SELECT
				pi.name as pi_name,
				pi.currency,
				pi.conversion_rate,
				pi.docstatus,
				pi.update_stock,
				pii.rate,
				pii.amount,
				pii.base_rate,
				pii.base_amount
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			WHERE pii.item_code = %s
				AND pi.import_file = %s
				AND pi.docstatus = 1
			ORDER BY pi.update_stock DESC, pi.posting_date DESC, pi.creation DESC
			LIMIT 1
			""",
			(item_code, import_file),
			as_dict=True,
		)
		if rows:
			return rows[0]
	return None


def get_vehicles_for_import_file(import_file):
	"""Items for an Import File.

	Match order:
	1. Import File.bl_number -> Item.custom_bl
	2. If BL blank, Import File.supplier_invoice_no -> Item.custom_bl
	3. Items on Purchase Invoices linked to this Import File (covers no-BL cars)

	Each vehicle includes purchase_price / purchase_currency / exchange_rate /
	purchase_amount_company from submitted PI (preferred) or Item.custom_price.
	"""
	if not import_file:
		return []
	row = frappe.db.get_value(
		"Import File",
		import_file,
		["bl_number", "supplier_invoice_no"],
		as_dict=True,
	)
	if not row:
		return []

	by_name = {}
	key = (row.bl_number or "").strip() or (row.supplier_invoice_no or "").strip()
	if key:
		for v in frappe.get_all(
			"Item",
			filters={"custom_bl": key, "disabled": 0},
			fields=[
				"name",
				"item_name",
				"custom_chassis_no",
				"custom_maker",
				"custom_m3",
				"custom_new_stock_id",
				"custom_price",
			],
			order_by="name asc",
		):
			by_name[v.name] = v

	# Fallback / supplement: cars already on a PI for this Import File (BL often N/A on MKT)
	pi_prices = {}
	if frappe.db.has_column("Purchase Invoice", "import_file"):
		pi_rows = frappe.db.sql(
			"""
			SELECT
				i.name, i.item_name, i.custom_chassis_no, i.custom_maker, i.custom_m3,
				i.custom_new_stock_id, i.custom_price,
				pii.rate as pi_rate, pii.base_rate, pii.base_amount,
				pi.currency as pi_currency, pi.conversion_rate, pi.docstatus, pi.update_stock,
				pi.modified as pi_modified
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			INNER JOIN `tabItem` i ON i.name = pii.item_code
			WHERE pi.import_file = %s
				AND pi.docstatus < 2
				AND IFNULL(i.disabled, 0) = 0
				AND IFNULL(pii.item_code, '') != ''
			ORDER BY
				pi.docstatus DESC,
				pi.update_stock DESC,
				pi.modified DESC,
				i.name
			""",
			import_file,
			as_dict=True,
		)
		for v in pi_rows:
			by_name.setdefault(v.name, v)
			# Prefer submitted stock PI row when several PIs exist
			existing = pi_prices.get(v.name)
			take = False
			if not existing:
				take = True
			elif flt(v.docstatus) == 1 and flt(existing.get("docstatus")) != 1:
				take = True
			elif (
				flt(v.docstatus) == flt(existing.get("docstatus"))
				and flt(v.update_stock) > flt(existing.get("update_stock") or 0)
			):
				take = True
			if take and flt(v.pi_rate) > 0:
				pi_prices[v.name] = {
					"purchase_price": flt(v.pi_rate),
					"purchase_currency": v.pi_currency or "JPY",
					"exchange_rate": flt(v.conversion_rate) or 1.0,
					"purchase_amount_company": flt(v.base_amount)
					or (flt(v.pi_rate) * (flt(v.conversion_rate) or 1.0)),
					"docstatus": v.docstatus,
					"update_stock": v.update_stock,
				}

	# Enrich purchase price on every vehicle
	for name, v in by_name.items():
		if name in pi_prices:
			v["purchase_price"] = pi_prices[name]["purchase_price"]
			v["purchase_currency"] = pi_prices[name]["purchase_currency"]
			v["exchange_rate"] = pi_prices[name]["exchange_rate"]
			v["purchase_amount_company"] = pi_prices[name]["purchase_amount_company"]
		else:
			v["purchase_price"] = flt(v.get("custom_price"))
			v["purchase_currency"] = "JPY" if flt(v.get("custom_price")) else None
			v["exchange_rate"] = 1.0
			v["purchase_amount_company"] = flt(v.get("custom_price"))

	return sorted(by_name.values(), key=lambda r: r.name or "")


def _is_stock_in_hand_account(account):
	"""Purchase cost (YEN) posts to Stock In Hand — not a distributeable IFCV expense."""
	if not account:
		return False
	if "stock in hand" in account.lower():
		return True
	account_type = frappe.db.get_value("Account", account, "account_type")
	return account_type == "Stock"


def distribution_method_from_costing(allocation_scope, entry_mode=None):
	"""Map Costing.allocation_scope → IFCV expense distribution_method.

	Costing is the source of truth (no voucher hardcoding).
	Legacy value \"By BL\" is treated as By BL Equal.
	Formula entry_mode (or scope By Formula) → split bulk JE via Costing.formula
	(e.g. Wharfage = TRA Duty × 7%), even when the JE itself is posted at BL level.
	"""
	if (entry_mode or "").strip() == "Formula" or (allocation_scope or "").strip() == "By Formula":
		return "By Formula"
	scope = (allocation_scope or "").strip()
	if scope == "By Vehicle":
		return "By Vehicle Manual"
	if scope == "By BL M3":
		return "By BL M3"
	if scope in ("By BL Equal", "By BL"):
		return "By BL Equal"
	return "By BL Equal"


def get_posted_expenses(import_file):
	"""Same source as csf_tz Landed Cost Voucher, plus Costing account mapping.

	Excludes Stock In Hand / Stock accounts (car purchase value, not landed expenses).
	Distribution method comes from Costing.allocation_scope.
	"""
	if not import_file:
		return []

	# custom_item / custom_chassis_no may not exist until migrate — guard SQL
	has_je_item = frappe.db.has_column("Journal Entry", "custom_item")
	item_col = "je.custom_item as linked_item," if has_je_item else "NULL as linked_item,"

	je_rows = frappe.db.sql(
		f"""
		SELECT
			jea.account as expense_account,
			COALESCE(NULLIF(je.user_remark, ''), je.title) as description,
			jea.debit_in_account_currency as amount,
			jea.account_currency as currency,
			je.name as source,
			{item_col}
			NULL as line_description
		FROM `tabJournal Entry` je
		INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
		WHERE je.import_file = %s
			AND je.docstatus = 1
			AND jea.debit_in_account_currency > 0
		""",
		import_file,
		as_dict=True,
	)

	pi_rows = frappe.db.sql(
		"""
		SELECT
			pii.expense_account as expense_account,
			pi.title as description,
			pii.net_amount as amount,
			pi.currency as currency,
			pi.name as source,
			NULL as linked_item,
			pii.item_code as line_description
		FROM `tabPurchase Invoice` pi
		INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
		WHERE pi.import_file = %s
			AND pi.docstatus = 1
			AND IFNULL(pii.net_amount, 0) > 0
		""",
		import_file,
		as_dict=True,
	)

	heads_by_account = {
		h.account: h
		for h in frappe.get_all(
			"Costing",
			filters={"disabled": 0, "account": ["is", "set"]},
			fields=[
				"name",
				"costing_code",
				"account",
				"allocation_scope",
				"currency",
				"entry_mode",
				"formula",
			],
		)
		if h.account
	}

	out = []
	for row in je_rows + pi_rows:
		if _is_stock_in_hand_account(row.expense_account):
			continue
		head = heads_by_account.get(row.expense_account)
		# Same account on multiple Costing heads: prefer Formula / explicit code match later on validate
		method = (
			distribution_method_from_costing(head.allocation_scope, entry_mode=head.entry_mode)
			if head
			else "By BL Equal"
		)
		currency = (
			row.currency
			or (head.currency if head else None)
			or frappe.db.get_value("Account", row.expense_account, "account_currency")
		)
		out.append(
			{
				"expense_account": row.expense_account,
				"description": _short_description(row.description),
				"amount": flt(row.amount),
				"currency": currency,
				"source": row.source,
				"costing_head": head.name if head else None,
				"costing_code": head.costing_code if head else None,
				"allocation_scope": head.allocation_scope if head else None,
				"entry_mode": head.entry_mode if head else None,
				"distribution_method": method,
				"linked_item": row.linked_item,
			}
		)
	return out


def _short_description(text, max_len=140):
	"""IFCV Expense.description is Data(140); JE remarks are often longer."""
	s = (text or "").strip()
	if len(s) <= max_len:
		return s
	return s[: max_len - 1].rstrip() + "…"


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def item_query_for_import_file(doctype, txt, searchfield, start, page_len, filters):
	"""Link query: Items belonging to the selected Import File."""
	import_file = (filters or {}).get("import_file")
	vehicles = get_vehicles_for_import_file(import_file) if import_file else []
	names = [v.name for v in vehicles]
	if not names:
		return []

	return frappe.db.sql(
		"""
		SELECT name, item_name, custom_chassis_no
		FROM `tabItem`
		WHERE name IN %(names)s
			AND disabled = 0
			AND (name LIKE %(txt)s OR IFNULL(item_name, '') LIKE %(txt)s
				OR IFNULL(custom_chassis_no, '') LIKE %(txt)s)
		ORDER BY name
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"names": names,
			"txt": f"%{txt}%",
			"start": start,
			"page_len": page_len,
		},
	)


@frappe.whitelist()
def load_from_import_file(import_file, distribution_basis=None):
	"""Load vehicles + expenses. distribution_basis is ignored — Costing controls split method."""
	if not import_file:
		frappe.throw(_("Import File is required"))

	vehicles = []
	for v in get_vehicles_for_import_file(import_file):
		vehicles.append(
			{
				"item": v.name,
				"chassis_no": v.custom_chassis_no,
				"maker": v.custom_maker,
				"m3": flt(v.custom_m3),
				"stock_id": v.custom_new_stock_id,
				"purchase_price": flt(v.get("purchase_price")),
				"purchase_currency": v.get("purchase_currency") or "JPY",
				"exchange_rate": flt(v.get("exchange_rate")) or 1.0,
				"purchase_amount_company": flt(v.get("purchase_amount_company")),
				"applicable_charges": 0,
			}
		)

	expenses = get_posted_expenses(import_file)
	return {"vehicles": vehicles, "expenses": expenses}


@frappe.whitelist()
def reload_from_import_file(docname):
	"""Reload vehicles/expenses from Import File, sync methods from Costing, rebuild allocations."""
	doc = frappe.get_doc("Import File Cost Voucher", docname)
	if not doc.import_file:
		frappe.throw(_("Import File is required"))

	data = load_from_import_file(doc.import_file)
	doc.set("vehicles", [])
	doc.set("expenses", [])
	doc.set("allocations", [])
	for v in data["vehicles"]:
		doc.append("vehicles", v)
	for e in data["expenses"]:
		doc.append("expenses", e)

	doc._sync_expense_distribution_from_costing()
	doc._distribute_allocations(keep_manual=False)
	doc.total_expense_amount = sum(flt(r.amount) for r in (doc.expenses or []))
	doc.total_allocated_amount = sum(flt(r.amount) for r in (doc.allocations or []))
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {
		"name": doc.name,
		"vehicles": len(doc.vehicles or []),
		"expenses": len(doc.expenses or []),
		"allocations": len(doc.allocations or []),
	}


@frappe.whitelist()
def get_import_file_items(import_file):
	return get_vehicles_for_import_file(import_file)


@frappe.whitelist()
def apply_manual_distribution(docname, row_idx, allocations):
	from frappe.utils import cint

	doc = frappe.get_doc("Import File Cost Voucher", docname)
	allocations = frappe.parse_json(allocations)
	row_idx = cint(row_idx)

	expense = None
	for r in doc.expenses or []:
		if r.idx == row_idx:
			expense = r
			break
	if not expense:
		frappe.throw(_("Expense row not found"))

	kept = [
		{
			"item": a.item,
			"chassis_no": a.chassis_no
			or frappe.db.get_value("Item", a.item, "custom_chassis_no"),
			"costing_head": a.costing_head,
			"account": a.account,
			"currency": a.currency,
			"amount": a.amount,
			"source_row": a.source_row,
		}
		for a in (doc.allocations or [])
		if a.source_row != row_idx
	]

	total = 0
	manual = []
	exp_currency = expense.currency or (
		frappe.db.get_value("Account", expense.expense_account, "account_currency")
		if expense.expense_account
		else None
	)
	for a in allocations:
		amount = flt(a.get("amount"))
		total += amount
		item_code = a.get("item")
		manual.append(
			{
				"item": item_code,
				"chassis_no": a.get("chassis_no")
				or frappe.db.get_value("Item", item_code, "custom_chassis_no"),
				"costing_head": expense.costing_head,
				"account": expense.expense_account,
				"currency": exp_currency,
				"amount": amount,
				"source_row": row_idx,
			}
		)

	if abs(total - flt(expense.amount)) > 0.5:
		frappe.throw(
			_("Manual allocations ({0}) must equal expense amount ({1})").format(total, expense.amount)
		)

	doc.set("allocations", kept + manual)
	# Rebuild auto rows while preserving this manual set
	doc._distribute_allocations(keep_manual=True)
	doc.total_expense_amount = sum(flt(r.amount) for r in (doc.expenses or []))
	doc.total_allocated_amount = sum(flt(r.amount) for r in (doc.allocations or []))
	doc.save()
	return doc.name
