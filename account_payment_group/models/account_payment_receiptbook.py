from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)


class AccountPaymentReceiptbook(models.Model):

    _inherit = 'account.payment.receiptbook'

    # sequence, name, partner_type, next_number, sequence_id, company_id,
    # prefix, active, mail_template_id ya están definidos en
    # account_payment_pro_receiptbook. Los sacamos de acá para no pisar
    # ese modelo (antes este archivo usaba _name en vez de _inherit,
    # definiendo un modelo aparte que tapaba document_type_id).

    # Único campo propio de este módulo, no existe en account_payment_pro_receiptbook.
    # Ningún talonario real lo usa hoy (todos en False/sin cargar), así que
    # lo dejamos con su default pero sin lógica especial en create().
    sequence_type = fields.Selection(
        [('automatic', 'Automatic'), ('manual', 'Manual')],
        string='Sequence Type',
        readonly=False,
        default='automatic',
    )
    padding = fields.Integer(
        'Number Padding',
        help="automatically adds some '0' on the left of the 'Number' to get "
        "the required padding size."
    )