{
    'name': 'AWS Integration',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Integración con AWS para lanzar instancias EC2',
    'description': """
        Módulo para lanzar y gestionar instancias EC2 en AWS desde Odoo.
        - Selección de AMIs actualizadas automáticamente
        - Lanzamiento de instancias con diferentes tipos
        - Gestión del estado de las instancias
    """,
    'author': 'Tu Empresa',
    'website': 'https://tusitio.com',
    'depends': ['base'],
    'data': [
        'views/aws_integration_views.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}