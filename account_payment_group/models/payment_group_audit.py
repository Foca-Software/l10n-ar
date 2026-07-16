import logging
from odoo import models, api, fields, _
from odoo.exceptions import UserError
from odoo.tools import formatLang
from markupsafe import Markup
_logger = logging.getLogger(__name__)
DELETE_GROUP = 'account.group_account_manager'
DEBT_LINE_VALS_KEYS = ('to_pay_move_line_ids', 'debt_move_line_ids')
AUDITED_BUTTONS = {'post': 'Validar (confirmar pago)', 'cancel': 'Cancelar', 'action_draft': 'Volver a borrador', 'confirm': 'Confirmar', 'compute_withholdings': 'Calcular retenciones'}
AUDITED_LINE_FIELDS = {'amount': 'Importe', 'journal_id': 'Diario', 'payment_method_line_id': 'Medio de pago', 'date': 'Fecha'}
AUDIT_FIELD_BLACKLIST = {'write_date', 'write_uid', 'create_date', 'create_uid', 'id', 'display_name', '__last_update', 'message_main_attachment_id', 'sent', 'pop_up', 'has_outstanding', 'has_outstandin', 'next_number', 'account_internal_type', 'localization', 'payment_methods', 'name', 'document_sequence_id', 'commercial_partner_id'}

class AccountPaymentGroup(models.Model):
    _inherit = 'account.payment.group'

    def write(self, vals):
        if self.env.context.get('skip_payment_audit'):
            return super().write(vals)
        fields_to_audit = [name for name in vals if self._is_auditable_field(name)]
        old_snapshot = {}
        if fields_to_audit:
            for rec in self:
                old_snapshot[rec.id] = {f: rec[f] for f in fields_to_audit}
        audit_debt = any((k in vals for k in DEBT_LINE_VALS_KEYS))
        if audit_debt:
            self._check_debt_lines_locked_by_payments()
        debt_before = {}
        if audit_debt:
            for rec in self:
                debt_before[rec.id] = set(rec.to_pay_move_line_ids.ids)
        result = super().write(vals)
        if audit_debt:
            AML = self.env['account.move.line']
            for rec in self:
                before = debt_before.get(rec.id, set())
                after = set(rec.to_pay_move_line_ids.ids)
                added = after - before
                removed = before - after
                if added or removed:
                    _logger.info('AUDIT RN6 grupo %s deudas +%s -%s', rec.id, list(added), list(removed))
                    rec._post_debt_lines_audit(AML.browse(list(added)), AML.browse(list(removed)))
        if fields_to_audit:
            labels = self.fields_get(fields_to_audit)
            for rec in self:
                changes = []
                for f in fields_to_audit:
                    old = old_snapshot[rec.id][f]
                    new = rec[f]
                    if old == new:
                        continue
                    changes.append((labels[f]['string'], rec._audit_field_value(f, old), rec._audit_field_value(f, new)))
                if changes:
                    _logger.info('AUDIT grupo %s cambios=%s', rec.id, [c[0] for c in changes])
                    rec._post_group_changed_audit(changes)
        return result

    def _check_debt_lines_locked_by_payments(self):
        """si el grupo ya tiene al menos un medio de pago cargado
        (payment_ids), no se permite agregar ni quitar líneas a pagar
        (to_pay_move_line_ids / debt_move_line_ids). Primero hay que
        eliminar los medios de pago cargados.
        """
        for rec in self:
            if rec.payment_ids:
                raise UserError(_(
                    'No se pueden modificar las líneas a pagar mientras '
                    'existan medios de pago cargados. Elimine primero los '
                    'medios de pago.'
                ))

    def _is_auditable_field(self, name):
        field = self._fields.get(name)
        if field is None:
            return False
        if name in AUDIT_FIELD_BLACKLIST:
            return False
        if not field.store:
            return False
        if field.compute and (not field.related):
            return False
        if field.type in ('one2many', 'many2many', 'binary'):
            return False
        if getattr(field, 'tracking', False):
            return False
        return True

    def _audit_field_value(self, field_name, value):
        field = self._fields[field_name]
        if value in (False, None, ''):
            return _('(vacío)')
        if field.type in ('monetary', 'float'):
            currency = self.currency_id or self.company_id.currency_id
            return formatLang(self.env, value, currency_obj=currency) if field.type == 'monetary' else formatLang(self.env, value)
        if field.type == 'many2one':
            return value.display_name or _('—')
        if field.type == 'selection':
            selection = dict(field._description_selection(self.env))
            return selection.get(value, value)
        if field.type == 'boolean':
            return _('Sí') if value else _('No')
        return str(value)

    def _post_group_changed_audit(self, changes):
        self.ensure_one()
        rows = Markup('').join((Markup('<li>%s: <i>%s</i> &rarr; <b>%s</b></li>') % (label, old, new) for label, old, new in changes))
        body = Markup(_('<b>Auditoría — Cambio en el grupo de pago</b><ul><li>Usuario: %(user)s</li><li>Fecha/hora: %(dt)s</li>%(rows)s</ul>')) % {'user': self.env.user.display_name, 'dt': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M:%S'), 'rows': rows}
        self._audit_message_post(body)

    def _audit_message_post(self, body):
        self.with_context(skip_payment_audit=True, mail_create_nolog=True).message_post(body=body, message_type='notification')

    def _debt_line_label(self, line):
        currency = line.currency_id or line.company_id.currency_id
        amount = formatLang(self.env, line.balance, currency_obj=currency)
        return _('%(move)s — %(account)s — %(partner)s (%(amount)s)') % {'move': line.move_id.display_name or line.name or _('—'), 'account': line.account_id.display_name or _('—'), 'partner': line.partner_id.display_name or _('—'), 'amount': amount}

    def _post_debt_lines_audit(self, added, removed):
        self.ensure_one()
        blocks = Markup('')
        if added:
            blocks += Markup('<li>Líneas agregadas:<ul>%s</ul></li>') % Markup('').join((Markup('<li>%s</li>') % self._debt_line_label(l) for l in added))
        if removed:
            blocks += Markup('<li>Líneas quitadas:<ul>%s</ul></li>') % Markup('').join((Markup('<li>%s</li>') % self._debt_line_label(l) for l in removed))
        body = Markup(_('<b>Auditoría — Líneas a pagar / Deudas</b><ul><li>Usuario: %(user)s</li><li>Fecha/hora: %(dt)s</li>%(blocks)s</ul>')) % {'user': self.env.user.display_name, 'dt': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M:%S'), 'blocks': blocks}
        self._audit_message_post(body)

    def _post_button_audit(self, label):
        for rec in self:
            body = Markup(_('<b>Auditoría — Acción de usuario: %(label)s</b><ul><li>Usuario: %(user)s</li><li>Fecha/hora: %(dt)s</li><li>Estado actual: %(state)s</li></ul>')) % {'label': label, 'user': self.env.user.display_name, 'dt': fields.Datetime.context_timestamp(rec, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M:%S'), 'state': rec.state or _('—')}
            rec._audit_message_post(body)

    def post(self):
        res = super().post()
        if not self.env.context.get('skip_payment_audit'):
            self._post_button_audit(AUDITED_BUTTONS['post'])
        return res

    def cancel(self):
        res = super().cancel()
        if not self.env.context.get('skip_payment_audit'):
            self._post_button_audit(AUDITED_BUTTONS['cancel'])
        return res

    def action_draft(self):
        res = super().action_draft()
        if not self.env.context.get('skip_payment_audit'):
            self._post_button_audit(AUDITED_BUTTONS['action_draft'])
        return res

    def confirm(self):
        res = super().confirm()
        if not self.env.context.get('skip_payment_audit'):
            self._post_button_audit(AUDITED_BUTTONS['confirm'])
        return res

    def compute_withholdings(self):
        res = super().compute_withholdings()
        if not self.env.context.get('skip_payment_audit'):
            self._post_button_audit(AUDITED_BUTTONS['compute_withholdings'])
        return res

    def unlink(self):
        self._check_payment_delete_allowed()
        return super().unlink()

    def _check_payment_delete_allowed(self):
        if self.env.su:
            return
        if not self.env.user.has_group(DELETE_GROUP):
            raise UserError(_('No tiene permisos para eliminar grupos de pago ni sus líneas. Solo un Administrador de Contabilidad puede hacerlo.\nSi necesita revertir un pago utilice la acción de Cancelar / Pasar a borrador.'))

    def _amount_label(self, payment):
        currency = payment.currency_id or payment.company_id.currency_id
        return formatLang(self.env, payment.amount, currency_obj=currency)

    def _post_line_created_audit(self, payment):
        self.ensure_one()
        body = Markup(_('<b>Auditoría — Alta de línea de pago</b><ul><li>Usuario: %(user)s</li><li>Fecha/hora: %(dt)s</li><li>Diario: %(journal)s</li><li>Importe: %(amount)s</li><li>Medio de pago: %(method)s</li><li>Referencia del grupo: %(ref)s</li></ul>')) % {'user': self.env.user.display_name, 'dt': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M:%S'), 'journal': payment.journal_id.display_name or _('—'), 'amount': self._amount_label(payment), 'method': payment.payment_method_line_id.display_name or _('—'), 'ref': self.display_name or self.name or _('—')}
        self._audit_message_post(body)

    def _post_line_deleted_audit(self, info):
        self.ensure_one()
        body = Markup(_('<b>Auditoría — Baja de línea de pago</b><ul><li>Usuario: %(user)s</li><li>Fecha/hora: %(dt)s</li><li>Línea eliminada: %(line)s</li><li>Diario: %(journal)s</li><li>Importe: %(amount)s</li><li>Medio de pago: %(method)s</li></ul>')) % {'user': self.env.user.display_name, 'dt': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M:%S'), 'line': info['name'], 'journal': info['journal'], 'amount': info['amount'], 'method': info['method']}
        self._audit_message_post(body)

    def _post_line_modified_audit(self, payment, changes):
        self.ensure_one()
        rows = Markup('').join((Markup('<li>%s: <i>%s</i> &rarr; <b>%s</b></li>') % (label, old, new) for label, old, new in changes))
        body = Markup(_('<b>Auditoría — Modificación de línea de pago</b><ul><li>Usuario: %(user)s</li><li>Fecha/hora: %(dt)s</li><li>Línea: %(line)s</li>%(rows)s</ul>')) % {'user': self.env.user.display_name, 'dt': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%d/%m/%Y %H:%M:%S'), 'line': payment.display_name or _('—'), 'rows': rows}
        self._audit_message_post(body)

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.model_create_multi
    def create(self, vals_list):
        explicit_group = [bool(v.get('payment_group_id')) for v in vals_list]
        payments = super().create(vals_list)
        if self._audit_enabled():
            for payment, had_group in zip(payments, explicit_group):
                group = payment.payment_group_id
                if group and had_group:
                    _logger.info('AUDIT RN1 (create) línea %s -> grupo %s', payment.id, group.id)
                    group._post_line_created_audit(payment)
        return payments

    def write(self, vals):
        audit = self._audit_enabled()
        tracked = {f for f in AUDITED_LINE_FIELDS if f in vals} if audit else set()
        setting_group = audit and 'payment_group_id' in vals and bool(vals.get('payment_group_id'))
        old_values = {}
        had_group_before = {}
        if audit:
            for payment in self:
                had_group_before[payment.id] = bool(payment.payment_group_id)
                if tracked and payment.payment_group_id:
                    old_values[payment.id] = {f: payment[f] for f in tracked}
        result = super().write(vals)
        if not audit:
            return result
        for payment in self:
            group = payment.payment_group_id
            if not group:
                continue
            if setting_group and (not had_group_before.get(payment.id)):
                _logger.info('AUDIT RN1 (write) línea %s -> grupo %s', payment.id, group.id)
                group._post_line_created_audit(payment)
                continue
            if payment.id not in old_values:
                continue
            changes = []
            for f in tracked:
                old = old_values[payment.id][f]
                new = payment[f]
                if old == new:
                    continue
                changes.append((AUDITED_LINE_FIELDS[f], self._audit_repr(f, old, payment), self._audit_repr(f, new, payment)))
            if changes:
                _logger.info('AUDIT RN2 (write) línea %s cambios=%s', payment.id, [c[0] for c in changes])
                group._post_line_modified_audit(payment, changes)
        return result

    def unlink(self):
        grouped = self.filtered('payment_group_id')
        if grouped and (not self.env.su) and (not self.env.user.has_group(DELETE_GROUP)):
            raise UserError(_('No tiene permisos para eliminar líneas de pago. Solo un Administrador de Contabilidad puede hacerlo.\nPara revertir el pago utilice Cancelar / Pasar a borrador.'))
        audit_data = []
        if self._audit_enabled():
            for payment in grouped:
                group = payment.payment_group_id
                currency = payment.currency_id or payment.company_id.currency_id
                audit_data.append((group, {'name': payment.display_name or _('—'), 'journal': payment.journal_id.display_name or _('—'), 'amount': formatLang(self.env, payment.amount or 0.0, currency_obj=currency), 'method': payment.payment_method_line_id.display_name or _('—')}))
        result = super().unlink()
        for group, info in audit_data:
            if group.exists():
                _logger.info('AUDIT RN8 baja línea %s del grupo %s', info['name'], group.id)
                group._post_line_deleted_audit(info)
        return result

    def _audit_enabled(self):
        ctx = self.env.context
        return not (ctx.get('skip_payment_audit') or ctx.get('created_automatically'))

    def _audit_repr(self, field_name, value, payment):
        if field_name == 'amount':
            currency = payment.currency_id or payment.company_id.currency_id
            return formatLang(self.env, value or 0.0, currency_obj=currency)
        if hasattr(value, 'display_name'):
            return value.display_name or _('—')
        return str(value) if value not in (False, None, '') else _('—')