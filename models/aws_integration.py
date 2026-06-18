import boto3
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class AwsIntegration(models.Model):
    _name = 'aws.integration'
    _description = 'Integración con AWS para levantar EC2'
    
    # ============================================================
    # Campos del modelo
    # ============================================================
    
    name = fields.Char(
        string='Nombre de la instancia', 
        required=True,
        help='Nombre que identificarán a la instancia en AWS'
    )
    
    # Campo para seleccionar la AMI
    ami_id = fields.Many2one(
        'aws.ami', 
        string='AMI (Sistema Operativo)',
        required=True,
        help='Selecciona el sistema operativo para la instancia'
    )
    
    # Campo para mostrar información de la AMI seleccionada
    ami_info = fields.Text(
        string='Información de la AMI',
        compute='_compute_ami_info',
        store=False
    )
    
    # Tipo de instancia
    instance_type = fields.Selection(
        selection=[
            ('t3.micro', 't3.micro (1 vCPU, 1 GB RAM)'),
            ('t3.small', 't3.small (2 vCPU, 2 GB RAM)'),
            ('t3.medium', 't3.medium (2 vCPU, 4 GB RAM)'),
            ('t3.large', 't3.large (2 vCPU, 8 GB RAM)'),
            ('t3.xlarge', 't3.xlarge (4 vCPU, 16 GB RAM)'),
        ],
        string='Tipo de instancia',
        required=True,
        default='t3.micro'
    )
    
    # Redes
    subnet_id = fields.Char(
        string='Subnet ID',
        required=True,
        help='ID de la subred donde se lanzará la instancia (ej: subnet-xxxxxxxx)'
    )
    
    # Key Pair
    key_name = fields.Char(
        string='Key Pair',
        required=True,
        help='Nombre del Key Pair para conectarse por SSH (ej: mi-key-pair)'
    )
    
    # Grupo de seguridad (opcional)
    security_group_ids = fields.Char(
        string='Grupos de Seguridad',
        help='IDs de los grupos de seguridad separados por comas (ej: sg-xxxx,sg-yyyy)'
    )
    
    # Estado de la instancia
    state = fields.Selection(
        selection=[
            ('pending', 'Pendiente'),
            ('running', 'En ejecución'),
            ('stopping', 'Deteniendo'),
            ('stopped', 'Detenida'),
            ('terminated', 'Terminada'),
            ('error', 'Error'),
        ],
        string='Estado',
        default='pending'
    )
    
    # ID de la instancia en AWS
    aws_instance_id = fields.Char(
        string='ID de instancia AWS',
        readonly=True,
        help='ID asignado por AWS a la instancia'
    )
    
    # IP Pública
    public_ip = fields.Char(
        string='IP Pública',
        readonly=True,
        help='Dirección IP pública de la instancia'
    )
    
    # Fechas
    launch_date = fields.Datetime(
        string='Fecha de lanzamiento',
        readonly=True
    )
    
    # ============================================================
    # Métodos computados
    # ============================================================
    
    @api.depends('ami_id')
    def _compute_ami_info(self):
        """Muestra información detallada de la AMI seleccionada"""
        for record in self:
            if record.ami_id:
                record.ami_info = f"""
Nombre: {record.ami_id.name}
AMI ID: {record.ami_id.ami_id}
Versión: {record.ami_id.version}
Arquitectura: {record.ami_id.architecture}
Fecha de creación: {record.ami_id.creation_date}
Descripción: {record.ami_id.description}
"""
            else:
                record.ami_info = "Selecciona una AMI para ver su información"
    
    # ============================================================
    # Métodos principales
    # ============================================================
    
    def action_launch_instance(self):
        """Lanza la instancia en AWS"""
        self.ensure_one()
        
        if not self.ami_id:
            raise UserError('Debes seleccionar una AMI')
        
        if not self.subnet_id:
            raise UserError('Debes especificar un Subnet ID')
        
        try:
            # Conectar a AWS (usando credenciales configuradas)
            ec2_client = self._get_ec2_client()
            
            # Preparar parámetros
            params = {
                'ImageId': self.ami_id.ami_id,
                'InstanceType': self.instance_type,
                'MinCount': 1,
                'MaxCount': 1,
                'SubnetId': self.subnet_id,
                'KeyName': self.key_name,
                'TagSpecifications': [{
                    'ResourceType': 'instance',
                    'Tags': [
                        {'Key': 'Name', 'Value': self.name},
                        {'Key': 'CreatedBy', 'Value': 'Odoo'},
                    ]
                }]
            }
            
            # Añadir grupos de seguridad si se especificaron
            if self.security_group_ids:
                sg_ids = [sg.strip() for sg in self.security_group_ids.split(',') if sg.strip()]
                if sg_ids:
                    params['SecurityGroupIds'] = sg_ids
            
            # Lanzar instancia
            response = ec2_client.run_instances(**params)
            
            # Guardar información de la instancia
            instance = response['Instances'][0]
            self.write({
                'aws_instance_id': instance['InstanceId'],
                'state': 'pending',
                'launch_date': fields.Datetime.now(),
            })
            
            # Mostrar notificación
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Instancia lanzada',
                    'message': f'Instancia {self.aws_instance_id} en proceso de creación',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error al lanzar instancia: {e}")
            raise UserError(f'Error al lanzar la instancia: {str(e)}')
    
    def action_refresh_state(self):
        """Actualiza el estado de la instancia desde AWS"""
        self.ensure_one()
        
        if not self.aws_instance_id:
            raise UserError('La instancia aún no ha sido lanzada')
        
        try:
            ec2_client = self._get_ec2_client()
            response = ec2_client.describe_instances(InstanceIds=[self.aws_instance_id])
            
            if response['Reservations']:
                instance = response['Reservations'][0]['Instances'][0]
                state_name = instance['State']['Name']
                
                self.write({
                    'state': state_name,
                    'public_ip': instance.get('PublicIpAddress', False),
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Estado actualizado',
                        'message': f'Estado: {state_name}',
                        'type': 'info',
                        'sticky': False,
                    }
                }
                
        except Exception as e:
            _logger.error(f"Error al actualizar estado: {e}")
            raise UserError(f'Error al actualizar estado: {str(e)}')
    
    def action_terminate_instance(self):
        """Termina la instancia en AWS"""
        self.ensure_one()
        
        if not self.aws_instance_id:
            raise UserError('La instancia aún no ha sido lanzada')
        
        if self.state in ['terminated']:
            raise UserError('La instancia ya está terminada')
        
        confirm = self.env['aws.terminate.wizard'].create({
            'instance_id': self.id,
            'instance_name': self.name,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirmar terminación',
            'res_model': 'aws.terminate.wizard',
            'res_id': confirm.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    # ============================================================
    # Métodos de ayuda
    # ============================================================
    
    def _get_ec2_client(self):
        """Obtiene el cliente EC2 de boto3 con las credenciales configuradas"""
        # Opción 1: Usar credenciales de AWS CLI (recomendado)
        try:
            return boto3.client('ec2', region_name='us-east-1')  # Cambia la región según tus necesidades
        except Exception as e:
            _logger.error(f"Error al conectar con AWS: {e}")
            raise UserError('Error al conectar con AWS. Verifica tus credenciales.')
        
        # Opción 2: Usar credenciales desde configuración de Odoo
        # aws_access_key = self.env['ir.config_parameter'].sudo().get_param('aws_access_key')
        # aws_secret_key = self.env['ir.config_parameter'].sudo().get_param('aws_secret_key')
        # aws_region = self.env['ir.config_parameter'].sudo().get_param('aws_region', 'us-east-1')
        # return boto3.client(
        #     'ec2',
        #     aws_access_key_id=aws_access_key,
        #     aws_secret_access_key=aws_secret_key,
        #     region_name=aws_region
        # )


class AwsAmi(models.Model):
    _name = 'aws.ami'
    _description = 'AMI de AWS'
    _order = 'creation_date desc'
    
    # ============================================================
    # Campos del modelo
    # ============================================================
    
    name = fields.Char(
        string='Nombre de la AMI',
        required=True,
        help='Nombre descriptivo de la AMI (ej: Ubuntu 24.04 LTS)'
    )
    
    ami_id = fields.Char(
        string='AMI ID',
        required=True,
        help='ID de la AMI en AWS (ej: ami-xxxxxxxx)'
    )
    
    version = fields.Char(
        string='Versión',
        help='Versión del sistema operativo (ej: 24.04, 22.04)'
    )
    
    architecture = fields.Selection(
        selection=[
            ('x86_64', 'x86_64 (64-bit)'),
            ('arm64', 'ARM64 (Graviton)'),
        ],
        string='Arquitectura',
        default='x86_64'
    )
    
    description = fields.Text(
        string='Descripción'
    )
    
    creation_date = fields.Char(
        string='Fecha de creación de la AMI',
        help='Fecha en que fue creada la AMI en AWS'
    )
    
    active = fields.Boolean(
        string='Activo',
        default=True,
        help='Si está activo, aparece en el selector'
    )
    
    is_official = fields.Boolean(
        string='AMI oficial',
        default=True,
        help='Indica si es una AMI oficial de Canonical/Amazon'
    )
    
    # ============================================================
    # Métodos para obtener AMIs desde AWS
    # ============================================================
    
    @api.model
    def action_refresh_from_aws(self):
        """Actualiza la lista de AMIs desde AWS"""
        try:
            ec2_client = boto3.client('ec2')
            
            # Definir las versiones de Ubuntu a buscar
            ubuntu_versions = [
                {'name': 'Ubuntu 24.04 LTS', 'version': '24.04', 'pattern': '*noble*'},
                {'name': 'Ubuntu 22.04 LTS', 'version': '22.04', 'pattern': '*jammy*'},
                {'name': 'Ubuntu 20.04 LTS', 'version': '20.04', 'pattern': '*focal*'},
                {'name': 'Ubuntu 18.04 LTS', 'version': '18.04', 'pattern': '*bionic*'},
            ]
            
            amis_created = 0
            
            for ubuntu in ubuntu_versions:
                # Buscar AMIs de Ubuntu
                response = ec2_client.describe_images(
                    Owners=['099720109477'],  # ID de Canonical
                    Filters=[
                        {'Name': 'name', 'Values': [f'*{ubuntu["version"]}*']},
                        {'Name': 'state', 'Values': ['available']},
                        {'Name': 'architecture', 'Values': ['x86_64']}
                    ]
                )
                
                if response['Images']:
                    # Ordenar por fecha y obtener la más reciente
                    images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
                    latest = images[0]
                    
                    # Verificar si ya existe
                    existing = self.search([('name', '=', ubuntu['name'])])
                    
                    if existing:
                        existing.write({
                            'ami_id': latest['ImageId'],
                            'description': latest.get('Description', '')[:200],
                            'creation_date': latest['CreationDate'],
                        })
                    else:
                        self.create({
                            'name': ubuntu['name'],
                            'ami_id': latest['ImageId'],
                            'version': ubuntu['version'],
                            'architecture': 'x86_64',
                            'description': latest.get('Description', '')[:200],
                            'creation_date': latest['CreationDate'],
                            'is_official': True,
                            'active': True,
                        })
                    
                    amis_created += 1
            
            # También añadir Amazon Linux como opción
            try:
                response = ec2_client.describe_images(
                    Owners=['amazon'],
                    Filters=[
                        {'Name': 'name', 'Values': ['al2023-ami-2023.*-kernel-*-x86_64']},
                        {'Name': 'state', 'Values': ['available']}
                    ]
                )
                
                if response['Images']:
                    images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
                    latest = images[0]
                    
                    existing = self.search([('name', '=', 'Amazon Linux 2023')])
                    if existing:
                        existing.write({
                            'ami_id': latest['ImageId'],
                            'description': latest.get('Description', '')[:200],
                            'creation_date': latest['CreationDate'],
                        })
                    else:
                        self.create({
                            'name': 'Amazon Linux 2023',
                            'ami_id': latest['ImageId'],
                            'version': '2023',
                            'architecture': 'x86_64',
                            'description': latest.get('Description', '')[:200],
                            'creation_date': latest['CreationDate'],
                            'is_official': True,
                            'active': True,
                        })
                    amis_created += 1
                    
            except Exception as e:
                _logger.warning(f"Error al obtener Amazon Linux: {e}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ AMIs actualizadas',
                    'message': f'Se actualizaron {amis_created} AMIs desde AWS',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error al actualizar AMIs: {e}")
            raise UserError(f'Error al actualizar AMIs: {str(e)}')
    
    @api.model
    def _get_ami_selection(self):
        """Obtiene las AMIs activas para el selector"""
        amis = self.search([('active', '=', True)])
        return [(ami.ami_id, ami.name) for ami in amis]


class AwsTerminateWizard(models.TransientModel):
    _name = 'aws.terminate.wizard'
    _description = 'Asistente para confirmar terminación de instancia'
    
    instance_id = fields.Many2one('aws.integration', string='Instancia', required=True)
    instance_name = fields.Char(string='Nombre de la instancia', readonly=True)
    
    def action_confirm_terminate(self):
        """Confirma y termina la instancia"""
        instance = self.instance_id
        
        try:
            ec2_client = boto3.client('ec2')
            ec2_client.terminate_instances(InstanceIds=[instance.aws_instance_id])
            
            instance.write({
                'state': 'terminated',
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Instancia terminada',
                    'message': f'La instancia {instance.name} ha sido terminada',
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            raise UserError(f'Error al terminar la instancia: {str(e)}')