#!/usr/bin/env python3

import sys
import os
import argparse
import boto3
from pathlib import Path
from typing import Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt

# Add the parent directory to sys.path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

# Importar el handler directamente
from app.functions.process_message.handler import handler

# Configurar entorno local
os.environ["STAGE"] = "dev"
os.environ["MAX_TOKENS"] = "3000"
os.environ["CATALOG_TABLE"] = "kavak-ai-agent-catalog-dev"
os.environ["EMBEDDINGS_TABLE"] = "kavak-ai-agent-embeddings-dev"
os.environ["CONVERSATIONS_TABLE"] = "kavak-ai-agent-conversations-dev"
os.environ["PROSPECTS_TABLE"] = "kavak-ai-agent-prospects-dev"

console = Console()

def get_user_id() -> str:
    """Solicita y valida el user_id al usuario."""
    while True:
        user_id = Prompt.ask("\n[bold blue]Ingresa tu user_id[/bold blue]")
        if user_id.strip():
            return user_id.strip()
        console.print("[red]El user_id no puede estar vacío[/red]")

def clean_conversation(conversation_id: str):
    """Limpia el historial de conversación directamente en DynamoDB local."""
    try:
        # Configurar cliente DynamoDB local
        dynamodb = boto3.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='dummy',
            aws_secret_access_key='dummy'
        )
        
        # Obtener tabla de conversaciones
        table = dynamodb.Table(os.environ["CONVERSATIONS_TABLE"])
        
        # Escanear y eliminar todos los mensajes del conversationId
        response = table.scan(
            FilterExpression='conversationId = :id',
            ExpressionAttributeValues={':id': conversation_id}
        )
        
        # Eliminar cada mensaje encontrado
        with table.batch_writer() as batch:
            for item in response.get('Items', []):
                batch.delete_item(
                    Key={
                        'conversationId': item['conversationId'],
                        'timestamp': item['timestamp']
                    }
                )
        
        console.print(f"[green]✓ Historial de conversación limpiado para {conversation_id}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error limpiando conversación: {str(e)}[/red]")

def chat(conversation_id: str, clean: bool = False):
    """Inicia una sesión de chat interactiva usando el handler de Lambda."""
    if clean:
        clean_conversation(conversation_id)
    
    console.print(Panel.fit(
        f"[bold blue]🤖 Chat Bot Kavak (Lambda Handler)[/bold blue]\n"
        f"Conversation ID: {conversation_id}\n"
        "Escribe tus mensajes y presiona Enter para chatear.\n"
        "Escribe 'salir' para terminar la conversación.\n"
        "Escribe 'limpiar' para borrar el historial.\n"
        "Escribe 'cambiar' para cambiar de usuario.",
        title="Bienvenido"
    ))
    
    while True:
        try:
            user_input = input("\nTú: ").strip()
            
            if user_input.lower() == 'salir':
                console.print("[yellow]¡Hasta luego! 👋[/yellow]")
                break
                
            if user_input.lower() == 'limpiar':
                clean_conversation(conversation_id)
                continue
                
            if user_input.lower() == 'cambiar':
                new_conversation_id = get_user_id()
                console.print(f"[yellow]Cambiando de usuario: {conversation_id} → {new_conversation_id}[/yellow]")
                conversation_id = new_conversation_id
                continue
                
            if not user_input:
                continue
            
            # Simular evento de Lambda
            event = {
                "from_number": conversation_id,  # Mantenemos from_number en el evento para compatibilidad
                "message_body": user_input
            }
            
            # Usar el handler directamente
            response = handler(event, None)
            agent_message = response.get("agent_message", "Lo siento, hubo un error procesando tu mensaje.")
            
            console.print(Panel(Markdown(agent_message), title="Bot"))
            
        except KeyboardInterrupt:
            console.print("\n[yellow]¡Hasta luego! 👋[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error inesperado: {str(e)}[/red]")

if __name__ == '__main__':
    # Configurar argumentos de línea de comandos
    parser = argparse.ArgumentParser(description='Chat Bot Kavak CLI')
    parser.add_argument('--clean', action='store_true', help='Limpiar historial de conversación antes de iniciar')
    parser.add_argument('--conversation-id', help='ID de la conversación a usar')
    args = parser.parse_args()
    
    # Verificar variables de entorno necesarias
    required_env_vars = ["OPENAI_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    
    if missing_vars:
        console.print(f"[red]Error: Faltan las siguientes variables de entorno: {', '.join(missing_vars)}[/red]")
        if "OPENAI_API_KEY" in missing_vars:
            console.print("Por favor, configura tu API key de OpenAI:")
            console.print("export OPENAI_API_KEY='tu-api-key'")
        sys.exit(1)
        
    # Verificar que DynamoDB local esté corriendo
    try:
        dynamodb = boto3.resource(
            'dynamodb',
            endpoint_url='http://localhost:8000',
            region_name='us-east-1',
            aws_access_key_id='dummy',
            aws_secret_access_key='dummy'
        )
        # Intentar listar tablas para verificar conexión
        dynamodb.meta.client.list_tables()
        console.print("[green]✓ Conectado a DynamoDB local[/green]")
    except Exception as e:
        console.print("[red]Error: No se pudo conectar a DynamoDB local[/red]")
        console.print("Asegúrate de que DynamoDB local esté corriendo:")
        console.print("docker run -d -p 8000:8000 amazon/dynamodb-local")
        sys.exit(1)
    
    # Obtener conversation_id (por argumento o interactivamente)
    conversation_id = args.conversation_id if args.conversation_id else get_user_id()
    chat(conversation_id, clean=args.clean) 