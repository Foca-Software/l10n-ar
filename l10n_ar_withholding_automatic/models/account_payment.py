from odoo import models, fields, _


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def compute_withholdings(self):
        self.ensure_one()

        # Solo procesar para proveedores
        if self.partner_type != 'supplier':
            return

        # Get alicuot
        arba_line = self._find_arba_alicuot()
        if not arba_line:
            return

        # Get padron type
        padron_type = self._find_padron_type(arba_line)
        if not padron_type or not padron_type.account_tax_retention_id:
            return

        # Get invoices being paid
        invoices = self.to_pay_move_line_ids.mapped('move_id')
        if not invoices:
            return

        total_debt_untaxed = sum(invoices.mapped('amount_untaxed'))
        total_alicuot = total_debt_untaxed * arba_line.alicuota_retencion / 100

        total_to_discount = self._total_amount_retention(
            padron_type.minimum_base_retention,
            arba_line.alicuota_retencion,
            padron_type.minimum_calcule_retention,
            invoices
        )

        display_msg = False
        if total_to_discount >= total_alicuot:
            display_msg = _(
                'La base/calculo mínimo de retención %.2f es mayor o igual que el monto sin '
                'impuestos de la factura, por lo que no se aplica en este pago'
            ) % padron_type.minimum_base_retention
        else:
            if total_to_discount > 0:
                display_msg = _(
                    'La base/calculo mínimo de retención %.2f es mayor que el monto sin impuestos '
                    'en algunas de las facturas, por lo que el siguiente descuento %.2f se aplica '
                    'a la retención total en este pago.'
                ) % (padron_type.minimum_base_retention, total_to_discount)

            amount_retention = total_alicuot - total_to_discount
            if amount_retention > 0:
                self._create_arba_withholding_line(
                    padron_type.account_tax_retention_id,
                    amount_retention,
                    total_debt_untaxed
                )
                # Actualizar el importe del pago restando la retención calculada (esto se aplica por petición de Maylin, para tener en cuenta la retención al total)
                self._onchange_withholdings()

        if display_msg:
            self.message_post(body=display_msg)

    def _find_arba_alicuot(self):
        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('to_date', '>=', self.date),
            ('from_date', '<=', self.date),
            ('company_id', '=', self.company_id.id),
        ]
        return self.env['res.partner.arba_alicuot'].search(domain, limit=1)

    def _find_padron_type(self, arba_line):
        return arba_line.padron_line_id.padron_type_id.filtered(
            lambda x: x.company_id.id == self.company_id.id
        )

    def _total_amount_retention(
        self,
        base_minimum_retention,
        percent_retention_arba,
        minimum_calcule_retention,
        invoices,
    ):
        total_to_discount = 0
        for invoice in invoices:
            if invoice.move_type in ["in_invoice", "in_refund"]:
                withholding_applied = invoice.amount_untaxed * percent_retention_arba / 100
                if base_minimum_retention > invoice.amount_untaxed:
                    total_to_discount += withholding_applied
                elif minimum_calcule_retention > withholding_applied:
                    total_to_discount += withholding_applied
        return total_to_discount

    def _create_arba_withholding_line(self, tax, amount_retention, base_retention):
        self.ensure_one()

        self.env['l10n_ar.payment.withholding'].create({
            'payment_id': self.id,
            'tax_id': tax.id,
            'base_amount': base_retention,
            'amount': amount_retention,
        })
