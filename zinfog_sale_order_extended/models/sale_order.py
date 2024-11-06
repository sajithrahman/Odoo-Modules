from odoo import fields, models, _
from odoo.exceptions import AccessError
from odoo.tools.float_utils import float_compare

class SaleOrder(models.Model):
    """
        Inherits from sale.order model to add additional fields and methods
        for managing order workflow and payment processes.
    """
    _inherit = "sale.order"

    manager_reference = fields.Text(string="Manager Reference", help="Manager's reference note for this specific sale order.")
    can_edit = fields.Boolean(compute='_compute_can_edit')
    auto_workflow = fields.Boolean(string="Auto Workflow")

    def _compute_can_edit(self):
        """
            Computes if the current user can edit the sale order.
        """
        can_edit = True if self.env.user.has_group('zinfog_sale_order_extended.group_sale_sales_admin') else False
        for user in self:
            user.can_edit = can_edit

    def _prepare_dict_account_payment(self, invoice):
        """
           Prepares dictionary values for account payment creation.
           Args:
               invoice (account.move): The invoice to be paid.
           Returns:
               dict: Dictionary with payment values.
        """
        partner_type = (
                invoice.move_type in ("out_invoice", "out_refund")
                and "customer"
                or "supplier"
        )
        return {
            "reconciled_invoice_ids": [(6, 0, invoice.ids)],
            "amount": invoice.amount_residual,
            "partner_id": invoice.partner_id.id,
            "partner_type": partner_type,
            "date": fields.Date.context_today(self),
            "currency_id": invoice.currency_id.id,
        }

    def _register_payment_invoice(self, invoice):
        """
            Registers and posts payment for an invoice and reconciles any outstanding amounts.
            Args:
                invoice (account.move): The invoice for which payment is registered.
            Returns:
                account.payment: The created payment record.
        """
        payment = self.env["account.payment"].create(
            self._prepare_dict_account_payment(invoice)
        )
        payment.action_post()
        domain = [
            ("account_type", "in", ("asset_receivable", "liability_payable")),
            ("reconciled", "=", False),
        ]
        payment_lines = payment.line_ids.filtered_domain(domain)
        lines = invoice.line_ids
        for account in payment_lines.account_id:
            (payment_lines + lines).filtered_domain(
                [("account_id", "=", account.id), ("reconciled", "=", False)]
            ).reconcile()
        return payment

    def action_confirm(self):
        """
              Confirms the sale order with additional validation for order limits
              and manages the auto workflow if enabled.
              Returns:
                  bool: The result of the action confirmation.
              Raises:
                  AccessError: If the order amount exceeds the limit and the user lacks the required access rights.
        """
        res = super().action_confirm()
        order_limit_amt = float(self.env['ir.config_parameter'].sudo().get_param('zinfog_sale_order_extended.sale_order_limit'))
        if order_limit_amt <= self.amount_total and self.can_edit == False:
            raise AccessError(_("Amount limit exceeded; requires Sale Admin access to confirm."))
        if self.auto_workflow:
            for pick in self.picking_ids:
                for move in pick.move_ids_without_package:
                    move.sudo().write({
                        'product_uom_qty': move.quantity  # updated the field a quantity_done to quantity
                    })
            self.sudo()._create_invoices()
            for inv in self.invoice_ids:
                inv.sudo().action_post()
                self._register_payment_invoice(inv)
        return res

class SaleOrderLineInherit(models.Model):
    """
        Inherits from sale.order.line model to add custom stock rule logic
        based on the auto workflow setting in the parent sale order.
    """
    _inherit = 'sale.order.line'

    def _action_launch_stock_rule(self, previous_product_uom_qty=False):
        """
            Overrides the method to launch stock rules with custom logic
            based on auto workflow flag in sale order.
            Args:
                previous_product_uom_qty (float, optional): The previous quantity for comparison. Defaults to False.
            Returns:
                bool: Result of the stock rule action.
        """
        # Custom logic before calling the super method
        if self.order_id.auto_workflow:
            if self._context.get("skip_procurement"):
                return True
            precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            procurements = []

            for line in self:
                line = line.with_company(line.company_id)
                if line.state != 'sale' or line.order_id.locked or not line.product_id.type in ('consu', 'product'):
                    continue
                qty = line._get_qty_procurement(previous_product_uom_qty)
                if float_compare(qty, line.product_uom_qty, precision_digits=precision) == 0:
                    continue

                group_id = self.env['procurement.group'].create(line._prepare_procurement_group_vals())
                line.order_id.procurement_group_id = group_id

                updated_vals = {}
                if group_id.partner_id != line.order_id.partner_shipping_id:
                    updated_vals.update({'partner_id': line.order_id.partner_shipping_id.id})
                if group_id.move_type != line.order_id.picking_policy:
                    updated_vals.update({'move_type': line.order_id.picking_policy})
                if updated_vals:
                    group_id.write(updated_vals)

                values = line._prepare_procurement_values(group_id=group_id)
                product_qty = line.product_uom_qty - qty

                line_uom = line.product_uom
                quant_uom = line.product_id.uom_id
                product_qty, procurement_uom = line_uom._adjust_uom_quantities(product_qty, quant_uom)
                procurements.append(line._create_procurement(product_qty, procurement_uom, values))

            if procurements:
                self.env['procurement.group'].run(procurements)

            # Trigger the Scheduler for Pickings
            orders = self.mapped('order_id')
            for order in orders:
                pickings_to_confirm = order.picking_ids.filtered(lambda p: p.state not in ['cancel', 'done'])
                if pickings_to_confirm:
                    pickings_to_confirm.action_confirm()

            # Call the super method at the end
            return super(SaleOrderLineInherit, self)._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)
        else:
            super(SaleOrderLineInherit, self)._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)
            return True
