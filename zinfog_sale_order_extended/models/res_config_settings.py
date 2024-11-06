from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    """
      Inherits configuration settings to add a sale order limit
      parameter for end-of-service settings in sales.
    """
    _inherit = 'res.config.settings'

    sale_order_limit = fields.Float(string="Sale Order Limit", config_parameter='zinfog_sale_order_extended.sale_order_limit')
