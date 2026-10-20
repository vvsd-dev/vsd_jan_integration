frappe.ui.form.on('Car Costing', {
	refresh(frm) {
		if (!frm.doc.usd_currency) {
			frm.set_value('usd_currency', 'USD');
		}
		hideActualOnCarCosting(frm);
		frm.add_custom_button(__('Load from Item'), () => loadFromItem(frm));
		frm.add_custom_button(__('Fetch Exchange Rates'), () => fetchRates(frm), __('Actions'));
		if (!frm.is_new()) {
			frm.add_custom_button(__('Recalculate'), () => recalc(frm), __('Actions'));
		}
	},

	item(frm) {
		if (frm.doc.item && frm.is_new()) loadFromItem(frm);
	},

	costing_date(frm) {
		if (frm.doc.costing_date) fetchRates(frm, false);
	},

	expected_selling_price(frm) {
		// City Levy / VAT formulas depend on ESP — recalc on change when doc saved
		if (!frm.is_new() && flt(frm.doc.expected_selling_price) >= 0) {
			recalc(frm);
		}
	},
});

function hideActualOnCarCosting(frm) {
	['tz_costing_lines', 'japan_costing_lines'].forEach(fieldname => {
		const field = frm.get_field(fieldname);
		if (!field || !field.grid) return;
		field.grid.update_docfield_property('actual_amount', 'hidden', 1);
		field.grid.update_docfield_property('actual_amount', 'in_list_view', 0);
		field.grid.refresh();
	});
}

function loadFromItem(frm) {
	if (!frm.doc.item) return frappe.msgprint(__('Please select an Item first.'));
	frappe.call({
		method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing.load_from_item',
		args: { docname: frm.is_new() ? null : frm.doc.name, item: frm.doc.item, import_file: frm.doc.import_file },
		freeze: true,
		freeze_message: __('Loading projected template...'),
		callback(r) {
			if (r.message) frappe.set_route('Form', 'Car Costing', r.message);
		}
	});
}

function fetchRates(frm, reload = true) {
	frappe.call({
		method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing.fetch_exchange_rates',
		args: {
			docname: frm.is_new() ? null : frm.doc.name,
			costing_date: frm.doc.costing_date,
		},
		freeze: true,
		freeze_message: __('Fetching Currency Exchange rates...'),
		callback(r) {
			if (!r.message) return;
			if (frm.is_new()) {
				if (r.message.exchange_rate) frm.set_value('exchange_rate', r.message.exchange_rate);
				if (r.message.yen_exchange_rate) frm.set_value('yen_exchange_rate', r.message.yen_exchange_rate);
			} else if (reload) {
				frm.reload_doc();
			}
			frappe.show_alert({
				message: __('TZS/USD: {0} | YEN/USD: {1}', [
					r.message.exchange_rate || '—',
					r.message.yen_exchange_rate || '—',
				]),
				indicator: r.message.exchange_rate ? 'green' : 'orange',
			});
		},
	});
}

function recalc(frm) {
	frappe.call({
		method: 'vsd_jan_integration.vsd_jan_international_customization.doctype.car_costing.car_costing.recalculate',
		args: { docname: frm.doc.name },
		freeze: true,
		callback(r) {
			if (r.message) {
				frm.reload_doc();
				frappe.show_alert({
					message: __('Projected Cost: {0} | Price: {1}', [format_currency(r.message.cost, 'TZS'), format_currency(r.message.price, 'TZS')]),
					indicator: 'green'
				});
			}
		}
	});
}
