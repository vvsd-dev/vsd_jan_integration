# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class ImportFileCostVoucher(Document):
	def validate(self):
		self._distribute_allocations()
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
		pi_groups = defaultdict(lambda: {"items": {}, "company": None, "grand_total": 0})
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
		"""Build LCV(s) from IFCV allocations.

		ERPNext allows only ONE tax row when Distribute Manually — so we create
		one LCV per expense account (each with that account's per-item charges).
		"""
		from collections import defaultdict

		from erpnext.controllers.taxes_and_totals import init_landed_taxes_and_totals

		company = group["company"]
		# Per-account, per-item amounts (already in company currency)
		by_account_item = defaultdict(lambda: defaultdict(float))
		for item_code in group["items"]:
			for acc, amt in (item_account_map.get(item_code) or {}).items():
				if flt(amt):
					by_account_item[acc][item_code] += flt(amt)

		if not by_account_item:
			return None

		cost_center = frappe.db.get_value("Company", company, "cost_center") or frappe.db.get_value(
			"Cost Center", {"company": company, "is_group": 0}, "name"
		)

		created_names = []
		# Cancel legacy multi-tax LCVs for this IFCV+PI (ERPNext forbids >1 tax on Distribute Manually)
		legacy = frappe.db.sql(
			"""
			SELECT DISTINCT lcv.name
			FROM `tabLanded Cost Voucher` lcv
			INNER JOIN `tabLanded Cost Purchase Receipt` lpr ON lpr.parent = lcv.name
			INNER JOIN `tabLanded Cost Taxes and Charges` lct ON lct.parent = lcv.name
			WHERE lpr.receipt_document = %s
				AND lcv.docstatus = 1
				AND lct.description LIKE %s
			""",
			(pi_name, f"%{self.name}%"),
		)
		for (lcv_name,) in legacy or []:
			tax_count = frappe.db.count("Landed Cost Taxes and Charges", {"parent": lcv_name})
			if tax_count > 1:
				try:
					frappe.get_doc("Landed Cost Voucher", lcv_name).cancel()
				except Exception:
					frappe.log_error(
						title=f"Cancel legacy LCV {lcv_name}",
						message=frappe.get_traceback(),
					)

		for acc, item_amounts in by_account_item.items():
			tax_total = sum(flt(v) for v in item_amounts.values())
			if not tax_total:
				continue

			desc = f"IFCV {self.name} / {acc}"
			# Skip if this IFCV already posted an LCV for this PI + expense account
			existing = frappe.db.sql(
				"""
				SELECT lcv.name
				FROM `tabLanded Cost Voucher` lcv
				INNER JOIN `tabLanded Cost Purchase Receipt` lpr ON lpr.parent = lcv.name
				INNER JOIN `tabLanded Cost Taxes and Charges` lct ON lct.parent = lcv.name
				WHERE lpr.receipt_document = %s
					AND lcv.docstatus = 1
					AND lct.expense_account = %s
					AND lct.description = %s
				LIMIT 1
				""",
				(pi_name, acc, desc),
			)
			if existing:
				created_names.append(existing[0][0])
				continue

			lcv = frappe.new_doc("Landed Cost Voucher")
			lcv.company = company
			lcv.posting_date = self.posting_date or frappe.utils.today()
			lcv.distribute_charges_based_on = "Distribute Manually"

			lcv.append(
				"purchase_receipts",
				{
					"receipt_document_type": "Purchase Invoice",
					"receipt_document": pi_name,
					"grand_total": group["grand_total"],
				},
			)

			lcv.append(
				"taxes",
				{
					"expense_account": acc,
					"description": desc,
					"amount": tax_total,
				},
			)

			for item_code, r in group["items"].items():
				charge = flt(item_amounts.get(item_code))
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
				continue

			# Reconcile rounding so applicable charges == tax amount (JPY→TZS FX)
			items_total = sum(flt(i.applicable_charges) for i in lcv.items)
			diff = flt(tax_total) - flt(items_total)
			if lcv.items and abs(diff) >= 0.0001:
				lcv.items[-1].applicable_charges = flt(lcv.items[-1].applicable_charges) + diff

			try:
				lcv.flags.ignore_permissions = True
				init_landed_taxes_and_totals(lcv)
				lcv.set_total_taxes_and_charges()
				# Re-apply tax amount after init (some versions overwrite)
				if lcv.taxes:
					lcv.taxes[0].amount = tax_total
				lcv.set_total_taxes_and_charges()
				items_total = sum(flt(i.applicable_charges) for i in lcv.items)
				diff = flt(lcv.total_taxes_and_charges) - flt(items_total)
				if lcv.items and abs(diff) >= 0.0001:
					lcv.items[-1].applicable_charges = flt(lcv.items[-1].applicable_charges) + diff
				lcv.insert(ignore_permissions=True)
				lcv.submit()
				created_names.append(lcv.name)
			except Exception:
				frappe.log_error(
					title=f"IFCV LCV {self.name} / {acc}",
					message=frappe.get_traceback(),
				)

		return ", ".join(created_names) if created_names else None

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
					}
				)
			)
		if rows:
			return rows
		return get_vehicles_for_import_file(self.import_file)

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
				self.append("allocations", a)
			return

		total_m3 = sum(flt(i.custom_m3) for i in items) or 0
		item_names = {i.name for i in items}
		chassis_to_item = {
			(frappe.db.get_value("Item", i.name, "custom_chassis_no") or "").upper(): i.name for i in items
		}

		for exp in self.expenses or []:
			if not flt(exp.amount):
				continue
			if exp.distribution_method == "By Vehicle Manual":
				kept = [a for a in manual_rows if a.get("source_row") == exp.idx]
				if kept:
					for a in kept:
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
					self.append(
						"allocations",
						{
							"item": matched,
							"costing_head": exp.costing_head,
							"account": exp.expense_account,
							"currency": exp.currency
							or (
								frappe.db.get_value("Account", exp.expense_account, "account_currency")
								if exp.expense_account
								else None
							),
							"amount": flt(exp.amount),
							"source_row": exp.idx,
						},
					)
				continue

			for item in items:
				if exp.distribution_method == "By BL M3":
					amount = (flt(exp.amount) * (flt(item.custom_m3) / total_m3)) if total_m3 else 0
				else:
					amount = flt(exp.amount) / len(items)

				self.append(
					"allocations",
					{
						"item": item.name,
						"costing_head": exp.costing_head,
						"account": exp.expense_account,
						"currency": exp.currency
						or (
							frappe.db.get_value("Account", exp.expense_account, "account_currency")
							if exp.expense_account
							else None
						),
						"amount": amount,
						"source_row": exp.idx,
					},
				)


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


def get_vehicles_for_import_file(import_file):
	"""Items for an Import File.

	Match order:
	1. Import File.bl_number -> Item.custom_bl
	2. If BL blank, Import File.supplier_invoice_no -> Item.custom_bl
	3. Items on Purchase Invoices linked to this Import File (covers no-BL cars)
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
			fields=["name", "item_name", "custom_chassis_no", "custom_maker", "custom_m3", "custom_new_stock_id"],
			order_by="name asc",
		):
			by_name[v.name] = v

	# Fallback / supplement: cars already on a PI for this Import File (BL often N/A on MKT)
	if frappe.db.has_column("Purchase Invoice", "import_file"):
		pi_rows = frappe.db.sql(
			"""
			SELECT DISTINCT
				i.name, i.item_name, i.custom_chassis_no, i.custom_maker, i.custom_m3, i.custom_new_stock_id
			FROM `tabPurchase Invoice Item` pii
			INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
			INNER JOIN `tabItem` i ON i.name = pii.item_code
			WHERE pi.import_file = %s
				AND pi.docstatus < 2
				AND IFNULL(i.disabled, 0) = 0
				AND IFNULL(pii.item_code, '') != ''
			ORDER BY i.name
			""",
			import_file,
			as_dict=True,
		)
		for v in pi_rows:
			by_name.setdefault(v.name, v)

	return sorted(by_name.values(), key=lambda r: r.name or "")


def _is_stock_in_hand_account(account):
	"""Purchase cost (YEN) posts to Stock In Hand — not a distributeable IFCV expense."""
	if not account:
		return False
	if "stock in hand" in account.lower():
		return True
	account_type = frappe.db.get_value("Account", account, "account_type")
	return account_type == "Stock"


def distribution_method_from_costing(allocation_scope):
	"""Map Costing.allocation_scope → IFCV expense distribution_method.

	Costing is the source of truth (no voucher hardcoding).
	Legacy value \"By BL\" is treated as By BL Equal.
	"""
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
			fields=["name", "costing_code", "account", "allocation_scope", "currency"],
		)
		if h.account
	}

	out = []
	for row in je_rows + pi_rows:
		if _is_stock_in_hand_account(row.expense_account):
			continue
		head = heads_by_account.get(row.expense_account)
		method = (
			distribution_method_from_costing(head.allocation_scope)
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
			}
		)

	expenses = get_posted_expenses(import_file)
	return {"vehicles": vehicles, "expenses": expenses}


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
		manual.append(
			{
				"item": a.get("item"),
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
