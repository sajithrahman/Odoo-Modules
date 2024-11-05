{
    'name': 'Sale Order Extended Management',
    'version': '17.0',
    'category': 'Sales',
    'summary': 'Extended management for sale orders with custom roles and workflow automation',
    'description': 'Extends the management features of Sale Orders, enabling custom user roles, field restrictions, order limits, and automated workflows for improved operational efficiency.',
    'author': "Sajith Rahman AM",
    'depends': ['base', 'sale'],
    'data': [
        'security/security.xml',
        'views/view_sale_order_inherit.xml',
        'views/view_res_config_settings_inherit.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
