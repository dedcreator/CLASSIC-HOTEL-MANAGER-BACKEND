# backend/menu/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Order, OrderItem
from django.contrib.auth import get_user_model

User = get_user_model()

class OrderConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.table_id = self.scope['url_route']['kwargs'].get('table_id')
        
        # Group name for all orders
        self.order_group_name = 'orders'
        
        # If table_id is provided, join table-specific group
        if self.table_id:
            self.table_group_name = f'orders_table_{self.table_id}'
            await self.channel_layer.group_add(
                self.table_group_name,
                self.channel_name
            )
        
        # Join general orders group
        await self.channel_layer.group_add(
            self.order_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send initial order status if table_id is provided
        if self.table_id:
            orders = await self.get_table_orders(self.table_id)
            await self.send(text_data=json.dumps({
                'type': 'initial_orders',
                'data': orders
            }))

    async def disconnect(self, close_code):
        # Leave groups
        await self.channel_layer.group_discard(
            self.order_group_name,
            self.channel_name
        )
        if hasattr(self, 'table_group_name'):
            await self.channel_layer.group_discard(
                self.table_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')
        
        if message_type == 'order_update':
            order_id = data.get('order_id')
            status = data.get('status')
            notes = data.get('notes')
            
            # Update order status
            order = await self.update_order_status(order_id, status, notes)
            
            if order:
                # Broadcast to all connected clients
                await self.channel_layer.group_send(
                    self.order_group_name,
                    {
                        'type': 'order_status_update',
                        'data': {
                            'order_id': order_id,
                            'status': status,
                            'order_number': order['order_number'],
                            'table_number': order['table_number'],
                            'total_amount': order['total_amount'],
                            'items': order['items'],
                            'updated_at': str(order['updated_at']),
                            'prepared_at': str(order['prepared_at']) if order['prepared_at'] else None,
                            'served_at': str(order['served_at']) if order['served_at'] else None,
                        }
                    }
                )
                
                # Also send to table-specific group
                if order['table_id']:
                    await self.channel_layer.group_send(
                        f'orders_table_{order["table_id"]}',
                        {
                            'type': 'order_status_update',
                            'data': {
                                'order_id': order_id,
                                'status': status,
                                'order_number': order['order_number'],
                                'table_number': order['table_number'],
                                'total_amount': order['total_amount'],
                                'items': order['items'],
                            }
                        }
                    )
        
        elif message_type == 'new_order':
            # New order placed
            order_data = data.get('data')
            await self.channel_layer.group_send(
                self.order_group_name,
                {
                    'type': 'new_order_notification',
                    'data': order_data
                }
            )
            
            # Also send to table-specific group
            if order_data.get('table_id'):
                await self.channel_layer.group_send(
                    f'orders_table_{order_data["table_id"]}',
                    {
                        'type': 'new_order_notification',
                        'data': order_data
                    }
                )

    async def order_status_update(self, event):
        # Send order status update to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'order_status_update',
            'data': event['data']
        }))

    async def new_order_notification(self, event):
        # Send new order notification to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'new_order',
            'data': event['data']
        }))

    @database_sync_to_async
    def get_table_orders(self, table_id):
        """Get orders for a specific table"""
        orders = Order.objects.filter(table_id=table_id).exclude(status__in=['paid', 'cancelled'])
        return [{
            'id': str(order.id),
            'order_number': order.order_number,
            'status': order.status,
            'total_amount': float(order.total_amount),
            'items': [{
                'item_name': item.item_name,
                'quantity': item.quantity,
                'unit_price': float(item.unit_price),
            } for item in order.order_items.all()],
            'placed_at': str(order.placed_at),
        } for order in orders]

    @database_sync_to_async
    def update_order_status(self, order_id, status, notes=None):
        """Update order status and return updated data"""
        try:
            order = Order.objects.get(id=order_id)
            order.status = status
            
            if status == 'preparing':
                order.prepared_at = timezone.now()
            elif status == 'served':
                order.served_at = timezone.now()
            elif status == 'paid':
                order.paid_at = timezone.now()
            
            if notes:
                order.notes = (order.notes + '\n' + notes) if order.notes else notes
            
            order.save()
            
            return {
                'id': str(order.id),
                'order_id': str(order.id),
                'order_number': order.order_number,
                'table_number': order.table.table_number,
                'table_id': str(order.table.id),
                'status': order.status,
                'total_amount': float(order.total_amount),
                'items': [{
                    'item_name': item.item_name,
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price),
                } for item in order.order_items.all()],
                'updated_at': order.updated_at,
                'prepared_at': order.prepared_at,
                'served_at': order.served_at,
            }
        except Order.DoesNotExist:
            return None