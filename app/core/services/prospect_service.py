import os
import json
import boto3
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from decimal import Decimal

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
        car_details: Dict[str, Any],
        status: str = "pending"
    ) -> bool:
        """
        Saves a new appointment for a prospect.
        
        Args:
            whatsapp_number: Prospect's WhatsApp number
            prospect_name: Name of the prospect
            appointment_date: Appointment date in YYYY-MM-DD format
            appointment_time: Appointment time in HH:MM format
            stock_id: Car's catalog ID
            car_details: Car details (make, model, version, etc.)
            status: Appointment status (pending, confirmed, cancelled)
            
        Returns:
            True if saved successfully
        """
        try:
            timestamp = datetime.utcnow().isoformat()
            appointment_id = f"{timestamp}#{whatsapp_number}"
            
            # Convert date and time to datetime for validation
            appointment_datetime = datetime.strptime(f"{appointment_date} {appointment_time}", "%Y-%m-%d %H:%M")
            
            # Validate that appointment is in the future
            if appointment_datetime < datetime.utcnow():
                print("[ERROR] Appointment date must be in the future")
                return False
            
            # Ensure car_details includes stockId
            if "stockId" not in car_details:
                car_details["stockId"] = stock_id
            
            item = {
                "whatsappNumber": whatsapp_number,
                "prospectName": prospect_name,
                "appointmentId": appointment_id,
                "createdAt": timestamp,
                "appointmentDate": appointment_date,
                "appointmentTime": appointment_time,
                "stockId": stock_id,
                "carDetails": car_details,
                "status": status,
                "lastUpdated": timestamp
            }
            
            # Save to DynamoDB
            self.table.put_item(Item=item)
            print(f"[DEBUG] Appointment saved successfully: {json.dumps(_convert_decimals(item), ensure_ascii=False)}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Error saving appointment: {str(e)}")
            import traceback
            print(f"[ERROR] Error traceback: {traceback.format_exc()}")
            return False

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
