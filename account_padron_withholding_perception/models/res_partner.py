# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = "res.partner"

    arba_alicuot_ids = fields.One2many(
        'res.partner.arba_alicuot',
        'partner_id',
        'Alícuotas PERC-RET',
    )
    line_padron_type_ids = fields.Many2many('account.padron.retention.perception.type',
                                    'res_partner_padron_type_rel',  'padron_type_id', 'partner_id',
                                    string="Rel Partner Patterns", copy=False, readonly=False)

    @api.model_create_multi
    def create(self, vals_list):
        records = super(ResPartner, self).create(vals_list)
        
        for record in records:
            if (
                record.country_id.code == 'AR' and
                record.l10n_ar_afip_responsibility_type_id.code not in ('5', '7', '8', '9') and
                record.l10n_latam_identification_type_id.name == 'CUIT' and
                self.env['ir.config_parameter'].sudo().get_param('account_padron_withholding_perception.check_census_on_create') and
                record.vat
            ):
                padrones = self.env['account.padron.retention.perception.type'].search([]).ids
                record.sudo().write({'line_padron_type_ids': [(6, 0, padrones)]})

        return records

    def write(self, vals):
        result = super(ResPartner, self).write(vals)

        for rec in self:
            if 'line_padron_type_ids' in vals:
                for line_obj in rec.line_padron_type_ids:
                    line_obj.partner_control()

                # Check if the 'line_padron_type_ids' field is not being unlinked
                if not any(op[0] == 3 for op in vals.get('line_padron_type_ids', [])):
                    rec.import_padron_server_partner()

        return result

    def import_padron_server_partner(self, context={}):
        partner_dic={} #padron_type_id
        for partner_obj in self:
            partner_dic[partner_obj.vat.replace("-", "")] = partner_obj
            context['partner_dic'] = partner_dic
            for padron_obj in partner_obj.line_padron_type_ids:
                result_ids = self.env['account.import.padron.ret.perc'].search([
                                                                ('padron_type_id', '=', padron_obj.id),
                                                                ('state','=', 'open')
                                                                ])
                for import_obj in result_ids:
                    import_obj.import_padron_server(context=context)

    def get_current_alicuota(self, padron_type, date_invoice, company_id):
        current_alicuota = None

        for alicuota in self.arba_alicuot_ids.filtered(lambda x: x.company_id.id == company_id.id):
            if alicuota.tag_id.id == padron_type.account_tag_perception_id.id:
                if alicuota.from_date <= date_invoice <= alicuota.to_date:
                    current_alicuota = alicuota
                    break

        return current_alicuota

    def process_partner_data(self, import_obj):
        line_padron = self.line_padron_type_ids.filtered(lambda line: line.id == import_obj.padron_type_id.id)
        if line_padron:
            self.write({
                'line_padron_type_ids': [(3, line_padron.id, False)]
            })


class ResPartnerArbaAlicuot(models.Model):
    """Partner ARBA Aliquot - Tax rates for withholdings and perceptions"""
    _name = "res.partner.arba_alicuot"
    _description = "Partner ARBA Aliquot"
    _order = "to_date desc, from_date desc, tag_id, company_id"

    _sql_constraints = [
            (
                'unique_alicuot_partner_period',
                'unique(partner_id, from_date, to_date, tag_id, company_id)',
                'Ya existe una alícuota para este socio, fecha y empresa.'
            )
        ]

    partner_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='cascade',
    )
    padron_line_id = fields.Many2one(
        'account.padron.retention.perception.line',
        string='Padron Line',
        ondelete='cascade',
    )
    tag_id = fields.Many2one(
        'account.account.tag',
        domain=[('applicability', '=', 'taxes')],
        required=False,
        help='Required only for perceptions. Not needed for retentions only.',
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        ondelete='cascade',
        default=lambda self: self.env.company,
    )
    from_date = fields.Date(
        string='From Date'
    )
    to_date = fields.Date(
        string='To Date'
    )
    numero_comprobante = fields.Char(
        string='Certificate Number'
    )
    codigo_hash = fields.Char(
        string='Hash Code'
    )
    alicuota_percepcion = fields.Float(
        string='Perception Rate'
    )
    alicuota_retencion = fields.Float(
        string='Withholding Rate'
    )
    grupo_percepcion = fields.Char(
        string='Perception Group'
    )
    grupo_retencion = fields.Char(
        string='Withholding Group'
    )
    withholding_amount_type = fields.Selection([
        ('untaxed_amount', 'Untaxed Amount'),
        ('total_amount', 'Total Amount'),
    ],
        string='Withholding Base',
        help='Base amount used to get withholding amount',
    )
    regimen_percepcion = fields.Char(
        size=3,
        string='Perception Regime',
        help="Used for SIRCAR TXT generation.\n"
        "Perception Regime Type (code according to table defined by jurisdiction)"
    )
    regimen_retencion = fields.Char(
        size=3,
        string='Withholding Regime',
        help="Used for SIRCAR TXT generation.\n"
        "Withholding Regime Type (code according to table defined by jurisdiction)"
    )
    api_codigo_articulo_retencion = fields.Selection([
        ('001', '001: Art.1 - inciso A - (Res. Gral. 15/97 y Modif.)'),
        ('002', '002: Art.1 - inciso B - (Res. Gral. 15/97 y Modif.)'),
        ('003', '003: Art.1 - inciso C - (Res. Gral. 15/97 y Modif.)'),
        ('004', '004: Art.1 - inciso D pto.1 - (Res. Gral. 15/97 y Modif.)'),
        ('005', '005: Art.1 - inciso D pto.2 - (Res. Gral. 15/97 y Modif.)'),
        ('006', '006: Art.1 - inciso D pto.3 - (Res. Gral. 15/97 y Modif.)'),
        ('007', '007: Art.1 - inciso E - (Res. Gral. 15/97 y Modif.)'),
        ('008', '008: Art.1 - inciso F - (Res. Gral. 15/97 y Modif.)'),
        ('009', '009: Art.1 - inciso H - (Res. Gral. 15/97 y Modif.)'),
        ('010', '010: Art.1 - inciso I - (Res. Gral. 15/97 y Modif.)'),
        ('011', '011: Art.1 - inciso J - (Res. Gral. 15/97 y Modif.)'),
        ('012', '012: Art.1 - inciso K - (Res. Gral. 15/97 y Modif.)'),
        ('013', '013: Art.1 - inciso L - (Res. Gral. 15/97 y Modif.)'),
        ('014', '014: Art.1 - inciso LL pto.1 - (Res. Gral. 15/97 y Modif.)'),
        ('015', '015: Art.1 - inciso LL pto.2 - (Res. Gral. 15/97 y Modif.)'),
        ('016', '016: Art.1 - inciso LL pto.3 - (Res. Gral. 15/97 y Modif.)'),
        ('017', '017: Art.1 - inciso LL pto.4 - (Res. Gral. 15/97 y Modif.)'),
        ('018', '018: Art.1 - inciso LL pto.5 - (Res. Gral. 15/97 y Modif.)'),
        ('019', '019: Art.1 - inciso M - (Res. Gral. 15/97 y Modif.)'),
        ('020', '020: Art.2 - (Res. Gral. 15/97 y Modif.)'),
    ],
        string='Withholding Article/Section Code',
    )
    api_codigo_articulo_percepcion = fields.Selection([
        ('021', '021: Art.10 - inciso A - (Res. Gral. 15/97 y Modif.)'),
        ('022', '022: Art.10 - inciso B - (Res. Gral. 15/97 y Modif.)'),
        ('023', '023: Art.10 - inciso D - (Res. Gral. 15/97 y Modif.)'),
        ('024', '024: Art.10 - inciso E - (Res. Gral. 15/97 y Modif.)'),
        ('025', '025: Art.10 - inciso F - (Res. Gral. 15/97 y Modif.)'),
        ('026', '026: Art.10 - inciso G - (Res. Gral. 15/97 y Modif.)'),
        ('027', '027: Art.10 - inciso H - (Res. Gral. 15/97 y Modif.)'),
        ('028', '028: Art.10 - inciso I - (Res. Gral. 15/97 y Modif.)'),
        ('029', '029: Art.10 - inciso J - (Res. Gral. 15/97 y Modif.)'),
        ('030', '030: Art.11 - (Res. Gral. 15/97 y Modif.)'),
    ],
        string='Perception Article/Section Code',
    )
    api_articulo_inciso_calculo_selection = [
        ('001', '001: Art. 5º 1er. párrafo (Res. Gral. 15/97 y Modif.)'),
        ('002', '002: Art. 5º inciso 1)(Res. Gral. 15/97 y Modif.)'),
        ('003', '003: Art. 5° inciso 2)(Res. Gral. 15/97 y Modif.)'),
        ('004', '004: Art. 5º inciso 4)(Res. Gral. 15/97 y Modif.)'),
        ('005', '005: Art. 5° inciso 5)(Res. Gral. 15/97 y Modif.)'),
        ('006', '006: Art. 6º inciso a)(Res. Gral. 15/97 y Modif.)'),
        ('007', '007: Art. 6º inciso b)(Res. Gral. 15/97 y Modif.)'),
        ('008', '008: Art. 6º inciso c)(Res. Gral. 15/97 y Modif.)'),
        ('009', '009: Art. 12º)(Res. Gral. 15/97 y Modif.)'),
        ('010', '010: Art. 6º inciso d)(Res. Gral. 15/97 y Modif.)'),
        ('011', '011: Art. 5° inciso 6)(Res. Gral. 15/97 y Modif.)'),
        ('012', '012: Art. 5° inciso 3)(Res. Gral. 15/97 y Modif.)'),
        ('013', '013: Art. 5° inciso 7)(Res. Gral. 15/97 y Modif.)'),
        ('014', '014: Art. 5° inciso 8)(Res. Gral. 15/97 y Modif.)'),
    ]
    api_articulo_inciso_calculo_percepcion = fields.Selection(
        api_articulo_inciso_calculo_selection,
        string='Perception Calculation Article/Section',
    )
    api_articulo_inciso_calculo_retencion = fields.Selection(
        api_articulo_inciso_calculo_selection,
        string='Withholding Calculation Article/Section',
    )