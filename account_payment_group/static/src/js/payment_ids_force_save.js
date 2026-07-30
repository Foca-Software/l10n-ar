/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

// El constrains _check_to_pay_move_line_ids_payment_group compara
// to_pay_move_line_ids de cada línea de pago contra el del recibo. Si se agrega
// una línea de pago antes de guardar el recibo (mismo diff sin persistir),
// esa línea puede quedar desincronizada y disparar el error. Forzamos el
// guardado del recibo antes de abrir el diálogo de alta de línea.
export class PaymentGroupPaymentIdsField extends X2ManyField {
    async onAdd(params) {
        const saved = await this.props.record.save();
        if (!saved) {
            return;
        }
        return super.onAdd(params);
    }
}

registry.category("fields").add("payment_group_payment_ids", {
    ...x2ManyField,
    component: PaymentGroupPaymentIdsField,
});
