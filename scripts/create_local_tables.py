import boto3
import os

# Configurar cliente de DynamoDB local
dynamodb = boto3.resource(
    'dynamodb',
    endpoint_url='http://localhost:8000',
    region_name='us-east-1',
    aws_access_key_id='dummy',
    aws_secret_access_key='dummy'
)

# Crear tabla de conversaciones
conversations_table = dynamodb.create_table(
    TableName='kavak-ai-agent-conversations-dev',
    KeySchema=[
        {
            'AttributeName': 'conversationId',
            'KeyType': 'HASH'  # Partition key
        },
        {
            'AttributeName': 'messageId',
            'KeyType': 'RANGE'  # Sort key
        }
    ],
    AttributeDefinitions=[
        {
            'AttributeName': 'conversationId',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'messageId',
            'AttributeType': 'S'
        }
    ],
    GlobalSecondaryIndexes=[
        {
            'IndexName': 'SummaryIndex',
            'KeySchema': [
                {
                    'AttributeName': 'conversationId',
                    'KeyType': 'HASH'
                }
            ],
            'Projection': {
                'ProjectionType': 'ALL'
            }
        }
    ],
    BillingMode='PAY_PER_REQUEST'
)

# Crear tabla de catálogo
catalog_table = dynamodb.create_table(
    TableName='kavak-ai-agent-catalog-dev',
    KeySchema=[
        {
            'AttributeName': 'stockId',
            'KeyType': 'HASH'  # Partition key
        }
    ],
    AttributeDefinitions=[
        {
            'AttributeName': 'stockId',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'make',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'model',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'price',
            'AttributeType': 'N'
        },
        {
            'AttributeName': 'year',
            'AttributeType': 'N'
        }
    ],
    GlobalSecondaryIndexes=[
        {
            'IndexName': 'MakeModelIndex',
            'KeySchema': [
                {
                    'AttributeName': 'make',
                    'KeyType': 'HASH'
                },
                {
                    'AttributeName': 'model',
                    'KeyType': 'RANGE'
                }
            ],
            'Projection': {
                'ProjectionType': 'ALL'
            }
        },
        {
            'IndexName': 'PriceYearIndex',
            'KeySchema': [
                {
                    'AttributeName': 'price',
                    'KeyType': 'HASH'
                },
                {
                    'AttributeName': 'year',
                    'KeyType': 'RANGE'
                }
            ],
            'Projection': {
                'ProjectionType': 'ALL'
            }
        }
    ],
    BillingMode='PAY_PER_REQUEST'
)

# Crear tabla de embeddings
embeddings_table = dynamodb.create_table(
    TableName='kavak-ai-agent-embeddings-dev',
    KeySchema=[
        {
            'AttributeName': 'stockId',
            'KeyType': 'HASH'  # Partition key
        },
        {
            'AttributeName': 'lastUpdate',
            'KeyType': 'RANGE'  # Sort key
        }
    ],
    AttributeDefinitions=[
        {
            'AttributeName': 'stockId',
            'AttributeType': 'S'
        },
        {
            'AttributeName': 'lastUpdate',
            'AttributeType': 'S'
        }
    ],
    GlobalSecondaryIndexes=[
        {
            'IndexName': 'LastUpdateIndex',
            'KeySchema': [
                {
                    'AttributeName': 'lastUpdate',
                    'KeyType': 'HASH'
                }
            ],
            'Projection': {
                'ProjectionType': 'ALL'
            }
        }
    ],
    BillingMode='PAY_PER_REQUEST'
)

print("Tablas creadas exitosamente:")
print("- kavak-ai-agent-conversations-dev")
print("- kavak-ai-agent-catalog-dev")
print("- kavak-ai-agent-embeddings-dev") 