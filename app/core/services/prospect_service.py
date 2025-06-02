import os
import json
import boto3
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
from core.services.car_recommender import CarRecommender

def _convert_decimals(obj):
    """
    Converts Decimal objects to int/float for JSON serialization.
    """
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimals(i) for i in obj]
    return obj

class ProspectService:
    """Service for handling prospect and appointment storage and management."""

    def __init__(self):
        """Initializes the service with the DynamoDB table."""
        self.table_name = os.environ.get('PROSPECTS_TABLE', f"kavak-ai-prospects-{os.environ.get('STAGE', 'dev')}")
        self.cars_table_name = os.environ.get('CARS_TABLE', f"kavak-ai-cars-{os.environ.get('STAGE', 'dev')}")
        self.car_recommender = CarRecommender()
        # Configure DynamoDB based on environment
        if os.environ.get('STAGE') == 'dev':
            self.dynamodb = boto3.resource(
                'dynamodb',
                endpoint_url='http://localhost:8000',
                region_name='us-east-1',
                aws_access_key_id='dummy',
                aws_secret_access_key='dummy'
            )
        else:
            self.dynamodb = boto3.resource('dynamodb')
            
        self.table = self.dynamodb.Table(self.table_name)
        print(f"[DEBUG] Using prospects table: {self.table_name}")

    def save_appointment(
        self,
        whatsapp_number: str,
        prospect_name: str,
        appointment_date: str,
        appointment_time: str,
        stock_id: str,
        status: str = "pending"
    ) -> Tuple[bool, str]:
        """
        Saves a new appointment for a prospect.
        First checks availability for the requested date and time.
        
        Args:
            whatsapp_number: Prospect's WhatsApp number
            prospect_name: Name of the prospect
            appointment_date: Appointment date in YYYY-MM-DD format
            appointment_time: Appointment time in HH:MM format
            stock_id: Car's catalog ID
            status: Appointment status (pending, confirmed, cancelled)
            
        Returns:
            Tuple of (success, message) where:
            - success is True if saved successfully
            - message contains success message or error description
        """
        try:
            print(f"[DEBUG] Intentando guardar cita para {whatsapp_number}")
            print(f"[DEBUG] Parámetros recibidos:")
            print(f"  - prospect_name: {prospect_name}")
            print(f"  - appointment_date: {appointment_date}")
            print(f"  - appointment_time: {appointment_time}")
            print(f"  - stock_id: {stock_id}")
            print(f"  - status: {status}")
            
            # First check availability
            print("[DEBUG] Verificando disponibilidad...")
            is_available = self.check_availability(appointment_date, appointment_time)
            if not is_available:
                print("[DEBUG] No hay disponibilidad para la fecha/hora solicitada")
                return False, "Lo siento, no hay disponibilidad para la fecha y hora solicitada. Por favor, intenta con otro horario."
            
            print("[DEBUG] Horario disponible, procediendo a guardar cita...")
            
            timestamp = datetime.utcnow().isoformat()
            appointment_id = f"{timestamp}#{whatsapp_number}"
            print(f"[DEBUG] Generated appointment_id: {appointment_id}")
            
            # Convert date and time to datetime for validation
            try:
                appointment_datetime = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %H:%M")
                print(f"[DEBUG] Parsed appointment_datetime: {appointment_datetime.isoformat()}")
            except ValueError as e:
                print(f"[ERROR] Error parsing date/time: {str(e)}")
                return False, "El formato de fecha u hora no es válido. Por favor, usa el formato YYYY-MM-DD para la fecha y HH:MM para la hora."
            
            # Validate that appointment is in the future
            if appointment_datetime < datetime.utcnow():
                print("[ERROR] Appointment date must be in the future")
                print(f"[DEBUG] Current time: {datetime.utcnow().isoformat()}")
                print(f"[DEBUG] Appointment time: {appointment_datetime.isoformat()}")
                return False, "La fecha y hora de la cita deben ser en el futuro."
            
            item = {
                "whatsappNumber": whatsapp_number,
                "prospectName": prospect_name,
                "appointmentId": appointment_id,
                "createdAt": timestamp,
                "appointmentDate": appointment_date,
                "appointmentTime": appointment_time,
                "stockId": stock_id,
                "status": status,
                "lastUpdated": timestamp
            }
            
            print(f"[DEBUG] Item a guardar: {json.dumps(_convert_decimals(item), ensure_ascii=False)}")
            print(f"[DEBUG] Usando tabla: {self.table_name}")
            
            # Save to DynamoDB
            try:
                response = self.table.put_item(Item=item)
                print(f"[DEBUG] Respuesta de DynamoDB: {json.dumps(_convert_decimals(response), ensure_ascii=False)}")
                print("[DEBUG] Appointment saved successfully")
                
                car = self.car_recommender.get_car_details(stock_id)
                car_description = f"{car.get('make', '')} {car.get('model', '')} {car.get('version', '')} {car.get('year', '')}".strip()
                success_message = f"¡Perfecto, {prospect_name}! Tu cita para ver el {car_description} está confirmada para el {appointment_date} a las {appointment_time}. Nos vemos en Kavak para que puedas conocer tu posible próximo auto. Si tienes alguna pregunta antes de tu cita, no dudes en contactarnos. ¡Te esperamos! 🚗✨"
                
                return True, success_message
            except Exception as e:
                print(f"[ERROR] Error en put_item: {str(e)}")
                import traceback
                print(f"[ERROR] Error traceback: {traceback.format_exc()}")
                return False, "Hubo un error al guardar la cita. Por favor, intenta de nuevo."
            
        except Exception as e:
            print(f"[ERROR] Error saving appointment: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return False, "Hubo un error al procesar tu solicitud. Por favor, intenta de nuevo."

    def get_prospect_appointments(
        self,
        whatsapp_number: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Gets a prospect's appointments.
        
        Args:
            whatsapp_number: Prospect's WhatsApp number
            status: Filter by status (optional)
            
        Returns:
            List of prospect's appointments
        """
        try:
            # Build filter expression
            filter_expression = None
            expression_values = {":num": whatsapp_number}
            
            if status:
                filter_expression = "status = :status"
                expression_values[":status"] = status
            
            # Query appointments
            response = self.table.query(
                KeyConditionExpression="whatsappNumber = :num",
                FilterExpression=filter_expression,
                ExpressionAttributeValues=expression_values,
                ScanIndexForward=False  # Descending order (most recent first)
            )
            
            return _convert_decimals(response.get("Items", []))
            
        except Exception as e:
            print(f"[ERROR] Error getting appointments: {str(e)}")
            return []

    def update_appointment_status(
        self,
        whatsapp_number: str,
        appointment_id: str,
        new_status: str
    ) -> bool:
        """
        Updates an appointment's status.
        
        Args:
            whatsapp_number: Prospect's WhatsApp number
            appointment_id: Appointment ID
            new_status: New appointment status
            
        Returns:
            True if updated successfully
        """
        try:
            # Validate status
            valid_statuses = ["pending", "confirmed", "cancelled", "completed"]
            if new_status not in valid_statuses:
                print(f"[ERROR] Invalid status: {new_status}")
                return False
            
            # Update status
            self.table.update_item(
                Key={
                    "whatsappNumber": whatsapp_number,
                    "appointmentId": appointment_id
                },
                UpdateExpression="SET status = :status, lastUpdated = :time",
                ExpressionAttributeValues={
                    ":status": new_status,
                    ":time": datetime.utcnow().isoformat()
                }
            )
            
            print(f"[DEBUG] Appointment status updated successfully to: {new_status}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Error updating appointment status: {str(e)}")
            return False

    def check_availability(
        self,
        date: str,
        time: str
    ) -> bool:
        """
        Checks availability for a specific date and time.
        
        Args:
            date: Date to check (YYYY-MM-DD)
            time: Time to check (HH:MM)
            
        Returns:
            True if available
        """
        try:
            # Query appointments for date and time using the DateStatusIndex
            # Use expression attribute names for both date and status to avoid reserved keywords
            response = self.table.query(
                IndexName="DateStatusIndex",
                KeyConditionExpression="#dt = :date AND #st = :status",
                FilterExpression="#tm = :time",
                ExpressionAttributeValues={
                    ":date": date,
                    ":time": time,
                    ":status": "confirmed"
                },
                ExpressionAttributeNames={
                    "#dt": "appointmentDate",  # Map 'appointmentDate' to '#dt'
                    "#st": "status",          # Map 'status' to '#st'
                    "#tm": "appointmentTime"  # Map 'appointmentTime' to '#tm'
                }
            )
            
            # For now, allow maximum 3 appointments per hour
            return len(response.get("Items", [])) < 3
            
        except Exception as e:
            print(f"[ERROR] Error checking availability: {str(e)}")
            return False
