from odoo import models, api

class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def button_cancel_reconciliation(self):
        payment_to_cancel = self.env['account.payment']
        for st_line in self:
            counterpart_lines = self.env['account.move.line']
            for line in st_line.move_id.line_ids:
                counterpart_lines |= line.matched_debit_ids.debit_move_id
                counterpart_lines |= line.matched_credit_ids.credit_move_id
            counterpart_lines = counterpart_lines - st_line.move_id.line_ids
            payment_to_cancel |= counterpart_lines.mapped('payment_id')
        payment_groups = payment_to_cancel.mapped('payment_group_id')
        res = self.action_undo_reconciliation()
        if payment_groups:
            payment_groups.write({'state': 'draft'})
            payment_groups.unlink()
        return res

    def process_reconciliation(self, counterpart_aml_dicts=None, payment_aml_rec=None, new_aml_dicts=None):
        self.ensure_one()
        if payment_aml_rec:
            own_line = self.move_id.line_ids.filtered(
                lambda l: not l.reconciled
                and l.account_id == payment_aml_rec.account_id
                and (l.debit > 0) != (payment_aml_rec.debit > 0)
            )
            if own_line:
                (own_line + payment_aml_rec).reconcile()
            # IMportante! hay que contemplar counterpart_aml_dicts / new_aml_dicts si algún otro
            # flujo del sistema los usa, si es asi hay que buscar la ruta de porque y cuando lo usa.
            # Para la incidencia SW-1846, se declaranan en none.
            return True
        return True