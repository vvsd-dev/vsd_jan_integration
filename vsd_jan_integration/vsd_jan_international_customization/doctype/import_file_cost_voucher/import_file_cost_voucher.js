// Copyright (c) 2026, VV Systems Developer LTD and contributors
// For license information, please see license.txt

frappe.ui.form.on('Import File Cost Voucher', {
	refresh(frm) {
		frm.add_custom_button(__('View by Vehicle'), () => openVehicleCostSummaryDialog(frm));
		frm.add_custom_button(__('Reload from Import File'), () => loadFromImportFile(frm), __('Actions'));
		frm.add_custom_button(__('Rebuild Allocations'), () => {
			frm.trigger('rebuild_allocations');
		}, __('Actions'));
		frm.add_custom_button(__('Distribute Manually'), () => openManualDistributionDialog(frm), __('Actions'));
	},

	import_file(frm) {
		if (!frm.doc.import_file) {
			frm.clear_table('vehicles');
			frm.clear_table('expenses');
			frm.clear_table('allocations');
			frm.refresh_fields(['vehicles', 'expenses', 'allocations']);
			return;
		}
		loadFromImportFile(frm);
	},

	rebuild_allocations(frm) {
		frm.save();
	},
});

function distributionMethodFromCosting(scope) {
	if (scope === 'By Vehicle') return 'By Vehicle Manual';
	if (scope === 'By BL M3') return 'By BL M3';
	if (scope === 'By BL Equal' || scope === 'By BL') return 'By BL Equal';
	return 'By BL Equal';
}

function amt(amount, currency) {
	return format_currency(amount, currency || null);
}

frappe.ui.form.on('Import File Cost Voucher Expense', {
	distribution_method(frm, cdt, cdn) {
		// Preview rebuilds on save; prompt for manual rows
		const row = locals[cdt][cdn];
		if (row.distribution_method === 'By Vehicle Manual' && !frm.is_new()) {
			frappe.show_alert({
				message: __('Use Actions → Distribute Manually for this expense row'),
				indicator: 'blue',
			});
		}
	},

	expense_account(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.expense_account) return;
		frappe.db.get_value('Account', row.expense_account, 'account_currency').then(r => {
			if (r.message && r.message.account_currency) {
				frappe.model.set_value(cdt, cdn, 'currency', r.message.account_currency);
			}
		});
	},

	costing_head(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.costing_head) return;
		frappe.db.get_value('Costing', row.costing_head, ['allocation_scope', 'account', 'costing_code', 'currency'])
			.then(r => {
				if (!r.message) return;
				frappe.model.set_value(
					cdt,
					cdn,
					'distribution_method',
					distributionMethodFromCosting(r.message.allocation_scope)
				);
				if (r.message.account && !row.expense_account) {
					frappe.model.set_value(cdt, cdn, 'expense_account', r.message.account);
				}
				if (r.message.currency) {
					frappe.model.set_value(cdt, cdn, 'currency', r.message.currency);
				}
			});
	},
});

function loadFromImportFile(frm) {
	if (!frm.doc.import_file) {
		frappe.msgprint(__('Please select an Import File first.'));
		return;
	}

	frappe.call({
		method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher.load_from_import_file',
		args: {
			import_file: frm.doc.import_file,
		},
		freeze: true,
		freeze_message: __('Loading vehicles and posted expenses...'),
		callback(r) {
			if (!r.message) return;

			frm.clear_table('vehicles');
			(r.message.vehicles || []).forEach(v => {
				const child = frm.add_child('vehicles');
				Object.keys(v).forEach(k => {
					child[k] = v[k];
				});
			});

			frm.clear_table('expenses');
			(r.message.expenses || []).forEach(e => {
				const child = frm.add_child('expenses');
				Object.keys(e).forEach(k => {
					child[k] = e[k];
				});
			});

			frm.clear_table('allocations');
			frm.refresh_fields(['vehicles', 'expenses', 'allocations']);

			const vCount = (r.message.vehicles || []).length;
			const eCount = (r.message.expenses || []).length;
			frappe.show_alert({
				message: __('Loaded {0} vehicles and {1} expense lines', [vCount, eCount]),
				indicator: vCount || eCount ? 'green' : 'orange',
			});
		},
	});
}

function openManualDistributionDialog(frm) {
	const rows = (frm.doc.expenses || []).filter(r => r.distribution_method === 'By Vehicle Manual');
	if (!rows.length) {
		frappe.msgprint(__('No expense rows set to By Vehicle Manual.'));
		return;
	}
	if (!(frm.doc.vehicles || []).length) {
		frappe.msgprint(__('No vehicles loaded. Select Import File first.'));
		return;
	}
	if (frm.is_new()) {
		frappe.msgprint(__('Please save the voucher before distributing manually.'));
		return;
	}

	const options = rows
		.map(r => {
			const label = r.costing_code || r.costing_head || r.expense_account;
			const hint = (r.description || r.source || '').toString().slice(0, 40);
			return `${r.idx}: ${label} — ${amt(r.amount, r.currency)}${hint ? ' | ' + hint : ''}`;
		})
		.join('\n');

	const d = new frappe.ui.Dialog({
		title: __('Distribute Expense to Vehicles'),
		size: 'extra-large',
		fields: [
			{
				fieldname: 'row_idx',
				fieldtype: 'Select',
				label: __('Expense Row'),
				options,
				reqd: 1,
				onchange() {
					buildVehicleAmountTable(d, frm);
				},
			},
			{
				fieldname: 'assign_all_to',
				fieldtype: 'Link',
				label: __('Quick: put full amount on one car'),
				options: 'Item',
				get_query() {
					const items = (frm.doc.vehicles || []).map(v => v.item);
					return { filters: { name: ['in', items] } };
				},
				onchange() {
					const item = d.get_value('assign_all_to');
					if (!item) return;
					const selected = d.get_value('row_idx');
					if (!selected) return;
					const rowIdx = cint(selected.split(':')[0]);
					const expense = (frm.doc.expenses || []).find(r => r.idx === rowIdx);
					if (!expense) return;
					const gridRows = d.fields_dict.vehicle_amounts.df.data || [];
					gridRows.forEach(r => {
						r.amount = r.item === item ? flt(expense.amount) : 0;
					});
					d.fields_dict.vehicle_amounts.grid.refresh();
					updateDialogSummary(d, frm);
				},
			},
			{
				fieldname: 'summary_html',
				fieldtype: 'HTML',
			},
			{
				fieldname: 'vehicle_amounts',
				fieldtype: 'Table',
				label: __('Amounts per Vehicle'),
				cannot_add_rows: true,
				in_place_edit: true,
				reqd: 1,
				fields: [
					{
						fieldname: 'item',
						fieldtype: 'Link',
						options: 'Item',
						label: __('Item'),
						in_list_view: 1,
						read_only: 1,
						columns: 3,
					},
					{
						fieldname: 'chassis_no',
						fieldtype: 'Data',
						label: __('Chassis'),
						in_list_view: 1,
						read_only: 1,
						columns: 2,
					},
					{
						fieldname: 'm3',
						fieldtype: 'Float',
						label: __('M3'),
						in_list_view: 1,
						read_only: 1,
						columns: 1,
					},
					{
						fieldname: 'amount',
						fieldtype: 'Currency',
						label: __('Amount'),
						in_list_view: 1,
						columns: 2,
						onchange() {
							updateDialogSummary(d, frm);
						},
					},
				],
			},
		],
		primary_action_label: __('Apply'),
		primary_action(values) {
			const rowIdx = cint((values.row_idx || '').split(':')[0]);
			const expense = (frm.doc.expenses || []).find(r => r.idx === rowIdx);
			const gridRows = d.fields_dict.vehicle_amounts.grid.get_data() || [];
			const allocations = gridRows
				.filter(r => flt(r.amount))
				.map(r => ({ item: r.item, amount: flt(r.amount) }));
			const total = allocations.reduce((s, a) => s + flt(a.amount), 0);

			if (Math.abs(total - flt(expense.amount)) > 0.5) {
				frappe.msgprint(
					__('Allocated {0} but expense is {1}. Adjust amounts to match.', [
						amt(total, expense.currency),
						amt(expense.amount, expense.currency),
					])
				);
				return;
			}

			frappe.call({
				method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher.apply_manual_distribution',
				args: {
					docname: frm.doc.name,
					row_idx: rowIdx,
					allocations: allocations,
				},
				freeze: true,
				callback() {
					d.hide();
					frm.reload_doc();
					frappe.show_alert({ message: __('Manual distribution applied'), indicator: 'green' });
				},
			});
		},
	});

	d.show();
	setTimeout(() => {
		if (rows.length >= 1) {
			d.set_value('row_idx', options.split('\n')[0]);
		}
		buildVehicleAmountTable(d, frm);
	}, 200);
}

function buildVehicleAmountTable(dialog, frm) {
	const selected = dialog.get_value('row_idx');
	if (!selected) return;
	const rowIdx = cint(selected.split(':')[0]);
	const expense = (frm.doc.expenses || []).find(r => r.idx === rowIdx);
	if (!expense) return;

	const existing = {};
	(frm.doc.allocations || [])
		.filter(a => a.source_row === rowIdx)
		.forEach(a => {
			existing[a.item] = flt(a.amount);
		});

	const equalShare = (frm.doc.vehicles || []).length
		? flt(expense.amount) / (frm.doc.vehicles || []).length
		: 0;

	// If JE title/description contains a chassis no, default full amount to that car
	const hint = `${expense.description || ''} ${expense.source || ''} ${expense.remarks || ''}`.toUpperCase();
	const matchedVehicle = (frm.doc.vehicles || []).find(v => {
		const ch = (v.chassis_no || '').toUpperCase();
		return ch && hint.includes(ch);
	});

	const rows = (frm.doc.vehicles || []).map(v => {
		let amount = equalShare;
		if (existing[v.item] != null) {
			amount = existing[v.item];
		} else if (matchedVehicle) {
			amount = v.item === matchedVehicle.item ? flt(expense.amount) : 0;
		}
		return {
			item: v.item,
			chassis_no: v.chassis_no,
			m3: v.m3,
			amount,
		};
	});

	dialog.fields_dict.vehicle_amounts.df.data = rows;
	dialog.fields_dict.vehicle_amounts.grid.refresh();

	if (matchedVehicle && !dialog.get_value('assign_all_to')) {
		dialog.set_value('assign_all_to', matchedVehicle.item);
	}
	updateDialogSummary(dialog, frm);
}

function updateDialogSummary(dialog, frm) {
	const selected = dialog.get_value('row_idx');
	if (!selected) return;
	const rowIdx = cint(selected.split(':')[0]);
	const expense = (frm.doc.expenses || []).find(r => r.idx === rowIdx);
	if (!expense) return;

	const gridRows = dialog.fields_dict.vehicle_amounts.grid.get_data() || [];
	const total = gridRows.reduce((s, r) => s + flt(r.amount), 0);
	const remaining = flt(expense.amount) - total;
	const ok = Math.abs(remaining) <= 0.5;
	dialog.fields_dict.summary_html.$wrapper.html(`
		<div style="padding:8px 0;font-size:13px;">
			<strong>${__('Expense')}:</strong> ${amt(expense.amount, expense.currency)}
			&nbsp;|&nbsp;
			<strong>${__('Allocated')}:</strong> ${amt(total, expense.currency)}
			&nbsp;|&nbsp;
			<strong style="color:${ok ? '#28a745' : '#dc3545'};">${__('Remaining')}: ${amt(remaining, expense.currency)}</strong>
		</div>
	`);
}

/* ── View by Vehicle: per-car allocation ledger ───────────────────────── */

function ensureVehicleSummaryStyles() {
	if (document.getElementById('ifcv-vehicle-summary-css')) return;
	const style = document.createElement('style');
	style.id = 'ifcv-vehicle-summary-css';
	style.textContent = `
		.ifcv-vs {
			--ink: #1c2430;
			--muted: #5c6b7a;
			--line: #d8dee6;
			--paper: #f7f5f1;
			--surface: #ffffff;
			--accent: #0f5c63;
			--accent-soft: #e6f1f2;
			--warn: #8a5a14;
			font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
			color: var(--ink);
			margin: -4px 0 4px;
		}
		.ifcv-vs__hero {
			background: linear-gradient(135deg, #1c2430 0%, #243447 58%, #1a4a50 100%);
			color: #f4f1ea;
			border-radius: 8px;
			padding: 16px 18px 14px;
			margin-bottom: 14px;
			box-shadow: 0 1px 0 rgba(255,255,255,0.06) inset;
		}
		.ifcv-vs__eyebrow {
			font-size: 10px;
			letter-spacing: 0.14em;
			text-transform: uppercase;
			opacity: 0.72;
			margin-bottom: 6px;
		}
		.ifcv-vs__title {
			font-family: "IBM Plex Serif", Georgia, serif;
			font-size: 18px;
			font-weight: 600;
			letter-spacing: -0.01em;
			margin: 0 0 10px;
			line-height: 1.25;
		}
		.ifcv-vs__meta {
			display: flex;
			flex-wrap: wrap;
			gap: 8px 18px;
			font-size: 12px;
			opacity: 0.9;
		}
		.ifcv-vs__meta span strong {
			font-weight: 600;
			opacity: 0.75;
			margin-right: 4px;
		}
		.ifcv-vs__stats {
			display: grid;
			grid-template-columns: repeat(3, 1fr);
			gap: 10px;
			margin-bottom: 14px;
		}
		.ifcv-vs__stat {
			background: var(--paper);
			border: 1px solid var(--line);
			border-radius: 6px;
			padding: 12px 14px;
		}
		.ifcv-vs__stat-label {
			font-size: 10px;
			letter-spacing: 0.1em;
			text-transform: uppercase;
			color: var(--muted);
			margin-bottom: 4px;
		}
		.ifcv-vs__stat-value {
			font-size: 16px;
			font-weight: 600;
			font-variant-numeric: tabular-nums;
			color: var(--ink);
		}
		.ifcv-vs__stat-value.is-accent { color: var(--accent); }
		.ifcv-vs__table-wrap {
			border: 1px solid var(--line);
			border-radius: 6px;
			overflow: hidden;
			background: var(--surface);
			max-height: 420px;
			overflow-y: auto;
		}
		.ifcv-vs__table {
			width: 100%;
			border-collapse: collapse;
			font-size: 12.5px;
		}
		.ifcv-vs__table thead th {
			position: sticky;
			top: 0;
			z-index: 1;
			background: #eef2f6;
			color: var(--muted);
			font-size: 10px;
			font-weight: 600;
			letter-spacing: 0.08em;
			text-transform: uppercase;
			text-align: left;
			padding: 10px 12px;
			border-bottom: 1px solid var(--line);
			white-space: nowrap;
		}
		.ifcv-vs__table thead th.amt,
		.ifcv-vs__table tbody td.amt {
			text-align: right;
			font-variant-numeric: tabular-nums;
		}
		.ifcv-vs__table thead th.num,
		.ifcv-vs__table tbody td.num {
			width: 42px;
			text-align: center;
			color: var(--muted);
			font-variant-numeric: tabular-nums;
			font-weight: 500;
		}
		.ifcv-vs__table tbody td {
			padding: 9px 12px;
			border-bottom: 1px solid #eef1f4;
			vertical-align: top;
		}
		.ifcv-vs__table tbody tr:nth-child(even) td { background: #fbfaf8; }
		.ifcv-vs__table tbody tr:hover td { background: var(--accent-soft); }
		.ifcv-vs__costing {
			font-weight: 600;
			color: var(--ink);
		}
		.ifcv-vs__sub {
			display: block;
			font-size: 11px;
			color: var(--muted);
			margin-top: 2px;
			font-weight: 400;
		}
		.ifcv-vs__pill {
			display: inline-block;
			font-size: 10px;
			font-weight: 600;
			letter-spacing: 0.02em;
			padding: 2px 7px;
			border-radius: 3px;
			background: #e8edf2;
			color: #3d4f5f;
			white-space: nowrap;
		}
		.ifcv-vs__pill--m3 { background: #e6f1f2; color: var(--accent); }
		.ifcv-vs__pill--manual { background: #f3ebe0; color: var(--warn); }
		.ifcv-vs__empty {
			padding: 36px 20px;
			text-align: center;
			color: var(--muted);
			font-size: 13px;
			background: var(--paper);
			border: 1px dashed var(--line);
			border-radius: 6px;
		}
		.ifcv-vs__foot {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-top: 12px;
			padding: 12px 14px;
			background: var(--ink);
			color: #f4f1ea;
			border-radius: 6px;
		}
		.ifcv-vs__foot-label {
			font-size: 11px;
			letter-spacing: 0.1em;
			text-transform: uppercase;
			opacity: 0.7;
		}
		.ifcv-vs__foot-value {
			font-size: 18px;
			font-weight: 600;
			font-variant-numeric: tabular-nums;
			font-family: "IBM Plex Serif", Georgia, serif;
		}
		@media (max-width: 720px) {
			.ifcv-vs__stats { grid-template-columns: 1fr; }
		}
	`;
	document.head.appendChild(style);

	if (!document.getElementById('ifcv-vehicle-summary-fonts')) {
		const link = document.createElement('link');
		link.id = 'ifcv-vehicle-summary-fonts';
		link.rel = 'stylesheet';
		link.href =
			'https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@600&display=swap';
		document.head.appendChild(link);
	}
}

function vehicleOptionLabel(v) {
	const chassis = v.chassis_no || __('No chassis');
	const maker = v.maker ? ` · ${v.maker}` : '';
	const stock = v.stock_id ? ` · ${v.stock_id}` : '';
	return `${chassis}${maker}${stock}`;
}

function methodPillClass(method) {
	if (method === 'By BL M3') return 'ifcv-vs__pill ifcv-vs__pill--m3';
	if (method === 'By Vehicle Manual') return 'ifcv-vs__pill ifcv-vs__pill--manual';
	return 'ifcv-vs__pill';
}

function shortMethod(method) {
	if (method === 'By BL Equal') return __('Equal');
	if (method === 'By BL M3') return __('M3');
	if (method === 'By Vehicle Manual') return __('Manual');
	return method || '—';
}

function openVehicleCostSummaryDialog(frm) {
	const vehicles = frm.doc.vehicles || [];
	if (!vehicles.length) {
		frappe.msgprint(__('No vehicles loaded. Select an Import File first.'));
		return;
	}
	if (!(frm.doc.allocations || []).length) {
		frappe.msgprint(__('No mapped allocations yet. Save the voucher or rebuild allocations first.'));
		return;
	}

	ensureVehicleSummaryStyles();

	const options = vehicles.map(v => ({
		label: vehicleOptionLabel(v),
		value: v.item,
	}));

	const d = new frappe.ui.Dialog({
		title: __('Vehicle Cost Summary'),
		size: 'extra-large',
		fields: [
			{
				fieldname: 'vehicle',
				fieldtype: 'Select',
				label: __('Vehicle'),
				options: options.map(o => o.value).join('\n'),
				reqd: 1,
				onchange() {
					renderVehicleCostSummary(d, frm);
				},
			},
			{
				fieldname: 'summary_html',
				fieldtype: 'HTML',
			},
		],
		primary_action_label: __('Close'),
		primary_action() {
			d.hide();
		},
	});

	// Replace raw item codes with readable labels on the select
	const $select = d.fields_dict.vehicle.$input;
	$select.empty();
	options.forEach(o => {
		$select.append(`<option value="${frappe.utils.escape_html(o.value)}">${frappe.utils.escape_html(o.label)}</option>`);
	});

	d.show();
	d.set_value('vehicle', options[0].value);
	renderVehicleCostSummary(d, frm);
}

function renderVehicleCostSummary(dialog, frm) {
	const item = dialog.get_value('vehicle');
	const $wrap = dialog.fields_dict.summary_html.$wrapper;
	if (!item) {
		$wrap.html(`<div class="ifcv-vs"><div class="ifcv-vs__empty">${__('Select a vehicle')}</div></div>`);
		return;
	}

	const vehicle = (frm.doc.vehicles || []).find(v => v.item === item);
	const expensesByIdx = {};
	(frm.doc.expenses || []).forEach(e => {
		expensesByIdx[e.idx] = e;
	});

	const rows = (frm.doc.allocations || [])
		.filter(a => a.item === item && flt(a.amount))
		.map(a => {
			const exp = a.source_row ? expensesByIdx[a.source_row] : null;
			const costing = a.costing_head || (exp && exp.costing_head) || '';
			return {
				costing,
				code: (exp && exp.costing_code) || costing || '',
				account: a.account || (exp && exp.expense_account) || '—',
				currency: a.currency || (exp && exp.currency) || '',
				method: (exp && exp.distribution_method) || '',
				source: (exp && exp.source) || '',
				description: (exp && (exp.description || exp.remarks)) || '',
				amount: flt(a.amount),
				source_row: a.source_row,
			};
		})
		.sort((a, b) => (a.costing || '').localeCompare(b.costing || ''));

	const paint = (nameMap) => {
		const byCurrency = {};
		rows.forEach(r => {
			const cur = r.currency || '—';
			byCurrency[cur] = (byCurrency[cur] || 0) + r.amount;
		});
		const totalsHtml = Object.keys(byCurrency)
			.map(cur => amt(byCurrency[cur], cur === '—' ? null : cur))
			.join(' · ');
		const voucherTotal =
			flt(frm.doc.total_allocated_amount) ||
			(frm.doc.allocations || []).reduce((s, a) => s + flt(a.amount), 0);
		const vehicleTotal = rows.reduce((s, r) => s + r.amount, 0);
		const sharePct = voucherTotal ? (vehicleTotal / voucherTotal) * 100 : 0;
		const lineCount = rows.length;

		const chassis = (vehicle && vehicle.chassis_no) || '—';
		const maker = (vehicle && vehicle.maker) || '—';
		const m3 = vehicle ? flt(vehicle.m3) : 0;
		const stock = (vehicle && vehicle.stock_id) || '—';

		let bodyHtml;
		if (!rows.length) {
			bodyHtml = `<div class="ifcv-vs__empty">${__('No amounts mapped to this vehicle yet.')}</div>`;
		} else {
			const trs = rows
				.map((r, i) => {
					const meta = (r.costing && nameMap[r.costing]) || {};
					const displayName = meta.costing_name || r.costing || '—';
					const code = meta.costing_code || r.code || '';
					return `
			<tr>
				<td class="num">${i + 1}</td>
				<td>
					<span class="ifcv-vs__costing">${frappe.utils.escape_html(displayName)}</span>
					${code ? `<span class="ifcv-vs__sub">${frappe.utils.escape_html(code)}</span>` : ''}
					${r.description ? `<span class="ifcv-vs__sub">${frappe.utils.escape_html(String(r.description).slice(0, 80))}</span>` : ''}
				</td>
				<td><span class="${methodPillClass(r.method)}">${frappe.utils.escape_html(shortMethod(r.method))}</span></td>
				<td>
					${frappe.utils.escape_html(r.source || '—')}
					${r.source_row ? `<span class="ifcv-vs__sub">${__('Expense row')} #${cint(r.source_row)}</span>` : ''}
				</td>
				<td>${frappe.utils.escape_html(r.account || '—')}</td>
				<td class="amt">${amt(r.amount, r.currency)}</td>
			</tr>`;
				})
				.join('');

			bodyHtml = `
			<div class="ifcv-vs__table-wrap">
				<table class="ifcv-vs__table">
					<thead>
						<tr>
							<th class="num">#</th>
							<th>${__('Costing')}</th>
							<th>${__('Method')}</th>
							<th>${__('Source')}</th>
							<th>${__('Account')}</th>
							<th class="amt">${__('Amount')}</th>
						</tr>
					</thead>
					<tbody>${trs}</tbody>
				</table>
			</div>
			<div class="ifcv-vs__foot">
				<div>
					<div class="ifcv-vs__foot-label">${__('Total allocated to this vehicle')}</div>
				</div>
				<div class="ifcv-vs__foot-value">${totalsHtml}</div>
			</div>`;
		}

		$wrap.html(`
		<div class="ifcv-vs">
			<div class="ifcv-vs__hero">
				<div class="ifcv-vs__eyebrow">${__('Mapped vehicle allocation')}</div>
				<div class="ifcv-vs__title">${frappe.utils.escape_html(chassis)}</div>
				<div class="ifcv-vs__meta">
					<span><strong>${__('Item')}</strong>${frappe.utils.escape_html(item)}</span>
					<span><strong>${__('Maker')}</strong>${frappe.utils.escape_html(maker)}</span>
					<span><strong>${__('M3')}</strong>${m3 || '—'}</span>
					<span><strong>${__('Stock ID')}</strong>${frappe.utils.escape_html(stock)}</span>
				</div>
			</div>
			<div class="ifcv-vs__stats">
				<div class="ifcv-vs__stat">
					<div class="ifcv-vs__stat-label">${__('Lines')}</div>
					<div class="ifcv-vs__stat-value">${lineCount}</div>
				</div>
				<div class="ifcv-vs__stat">
					<div class="ifcv-vs__stat-label">${__('Vehicle total')}</div>
					<div class="ifcv-vs__stat-value is-accent">${totalsHtml || amt(0)}</div>
				</div>
				<div class="ifcv-vs__stat">
					<div class="ifcv-vs__stat-label">${__('Share of voucher')}</div>
					<div class="ifcv-vs__stat-value">${sharePct.toFixed(1)}%</div>
				</div>
			</div>
			${bodyHtml}
		</div>
	`);
	};

	dialog._ifcv_costing_names = dialog._ifcv_costing_names || {};
	const heads = [...new Set(rows.map(r => r.costing).filter(Boolean))];
	const missing = heads.filter(h => !dialog._ifcv_costing_names[h]);

	if (!missing.length) {
		paint(dialog._ifcv_costing_names);
		return;
	}

	frappe.db
		.get_list('Costing', {
			filters: { name: ['in', missing] },
			fields: ['name', 'costing_name', 'costing_code'],
			limit: missing.length,
		})
		.then(list => {
			(list || []).forEach(h => {
				dialog._ifcv_costing_names[h.name] = h;
			});
			paint(dialog._ifcv_costing_names);
		})
		.catch(() => paint(dialog._ifcv_costing_names));
}

