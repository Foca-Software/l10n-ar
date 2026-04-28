# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Import Padron Withholding and Perception",
    "summary": """
        Adds to the partner the possibility of importing Patterns
        of Withholdings and Perceptions.
    """,
    "author": "Calyx Servicios S.A.",
    "maintainers": ["PerezGabriela", "leandro090685"],
    "website": "http://odoo.calyx-cloud.com.ar/",
    "license": "AGPL-3",
    "category": "Account",
    "version": "18.0.7.1.0",
    "installable": True,
    "application": False,
    "depends": [
        'l10n_ar_tax_ratio',
        'l10n_ar_tax_backward_compatibility',
        'l10n_ar_tax',
        'l10n_ar_tax_python',
        'l10n_account_withholding_tax',
        'l10n_ar_payment_bundle',
        'l10n_ar_withholding',
        'account_payment_group',
    ],
    "data": [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/account_import_padron_ret_perc_view.xml',
        # 'views/account_move_view.xml',
        'views/account_padron_retention_perception_type_view.xml',
        'views/res_partner_view.xml',
        'views/account_tax_view.xml',
    ],
}
