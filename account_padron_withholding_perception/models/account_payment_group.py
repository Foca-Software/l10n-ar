from odoo import models, _
from odoo.exceptions import UserError


class AccountPaymentGroup(models.Model):
    _inherit = "account.payment.group"


    def compute_withholdings(self):
        self.ensure_one()

        result = super(AccountPaymentGroup, self).compute_withholdings()

        # Solo procesar para proveedores
        if self.partner_type != 'supplier':
            return result

        # Get alicuot
        arba_line = self._find_arba_alicuot()
        if not arba_line:
            return result

        # Get padron type
        padron_type = self._find_padron_type(arba_line)
        if not padron_type or not padron_type.account_tax_retention_id:
            return result

        # Get all debt lines
        to_pay_lines = self._get_all_to_pay_lines()
        if not to_pay_lines:
            return result

        total_debt_untaxed = sum(to_pay_lines.mapped('move_id.amount_untaxed'))
        total_alicuot = total_debt_untaxed * arba_line.alicuota_retencion / 100

        total_to_discount = self._total_amount_retention(
            padron_type.minimum_base_retention, 
            arba_line.alicuota_retencion, 
            padron_type.minimum_calcule_retention
        )

        display_msg = False
        if total_to_discount >= total_alicuot:
            display_msg = _(
                'The minimum base/calculated withholding {} is higher or equal than the untaxed amount '
                'in the invoice, so it is not applied in this payment'
            ).format(padron_type.minimum_base_retention)
        else:
            if total_to_discount > 0:
                display_msg = _(
                    'The minimum base/calculated withholding {} is higher than the untaxed amount '
                    'on some of the invoices, so the following discount {} is applied to '
                    'withholding on the total in this payment.'
                ).format(padron_type.minimum_base_retention, total_to_discount)

            amount_retention = total_alicuot - total_to_discount
            if amount_retention > 0:
                self._create_arba_withholding_payment(
                    padron_type.account_tax_retention_id,
                    amount_retention,
                    total_debt_untaxed
                )

        if display_msg:
            self.message_post(body=display_msg)
        
        return result


    def _find_arba_alicuot(self):
        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('to_date', '>=', self.payment_date),
            ('from_date', '<=', self.payment_date),
            ('company_id', '=', self.company_id.id),
        ]
        return self.env['res.partner.arba_alicuot'].search(domain, limit=1)


    def _find_padron_type(self, arba_line):
        return arba_line.padron_line_id.padron_type_id.filtered(
            lambda x: x.company_id.id == self.company_id.id
        )


    def _total_amount_retention(self, base_minimum_retention, percent_retention_arba, minimum_calcule_retention):
        """
        Calculate the total amount to be retained based on specified criteria.

        :param base_minimum_retention: Minimum base for retention.
        :param percent_retention_arba: ARBA retention percentage.
        :param minimum_calcule_retention: Minimum calculated retention amount.
        :return: Total amount to be retained.
        """
        total_to_discount = 0
        for move_line in self.to_pay_move_line_ids:
            if move_line.move_id.move_type in ["in_invoice", "in_refund"]:
                withholding_applied = (
                    move_line.move_id.amount_untaxed * percent_retention_arba / 100
                )
                if base_minimum_retention > move_line.move_id.amount_untaxed:
                    total_to_discount += withholding_applied
                else:
                    if minimum_calcule_retention > withholding_applied:
                        total_to_discount += withholding_applied
        return total_to_discount


    def _get_all_to_pay_lines(self):
        return self.to_pay_move_line_ids.filtered(lambda x: x.move_id.move_type in ["in_invoice", "in_refund"])


    def _create_arba_withholding_payment(self, tax, amount_retention, base_retention):
        self.ensure_one()

        config_param = self.env['ir.config_parameter'].sudo()

        journal_id = config_param.get_param(
            'account_padron_withholding_perception.arba_withholding_journal_id'
        )

        if not journal_id:
            raise UserError(_("Configure an ARBA Withholding Journal in Accounting Settings."))

        withholding_journal = self.env['account.journal'].browse(int(journal_id))

        if withholding_journal.company_id != self.company_id:
            raise UserError(_("The ARBA journal must belong to the same company as the payment group."))

        # reutilizamos método de pago del grupo si existe
        payment_method_line = withholding_journal.outbound_payment_method_line_ids[:1]

        if not payment_method_line:
            raise UserError(_("The selected journal has no outbound payment method configured."))

        payment_vals = {
            'payment_group_id': self.id,
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner_id.id,
            'amount': amount_retention,
            'currency_id': self.currency_id.id,
            'date': self.payment_date,
            'journal_id': withholding_journal.id,
            'payment_method_line_id': payment_method_line.id,
            'memo': _('ARBA Withholding - Tax: %s') % tax.name,
        }

        self.env['account.payment'].create(payment_vals)
