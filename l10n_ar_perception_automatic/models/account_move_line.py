from odoo import models, api, fields
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.onchange('product_id', 'tax_ids')
    def onchange_product_id_perception(self):
        # NO agregar automáticamente el impuesto
        # Solo se agrega cuando se presiona el botón calculate_perceptions
        return

    def _get_price_total_and_subtotal(
                self, price_unit=None, quantity=None, discount=None, currency=None,
                product=None, partner=None, taxes=None, move_type=None):
            invoice = self.move_id.reversed_entry_id or self.move_id
            invoice_date = invoice.invoice_date or fields.Date.context_today(self)
            if not partner and invoice.partner_id:
                partner = invoice.partner_id
            context_dict = {'invoice_date': invoice_date, 'date': invoice_date}
            if invoice.partner_id:
                context_dict['partner_id'] = invoice.partner_id.id
            self = self.with_context(**context_dict)
            return super(AccountMoveLine, self)._get_price_total_and_subtotal(
                price_unit=price_unit, quantity=quantity, discount=discount, currency=currency,
                product=product, partner=partner, taxes=taxes, move_type=move_type)