#!/bin/bash

# Colores para mensajes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que DynamoDB local está corriendo
echo -e "${YELLOW}🔍 Verificando DynamoDB local...${NC}"
if ! curl -s http://localhost:8000 > /dev/null; then
    echo -e "${RED}❌ DynamoDB local no está corriendo en http://localhost:8000${NC}"
    exit 1
fi

# Función para crear tabla y verificar que se creó
create_table() {
    local table_name=$1
    local create_cmd=$2
    
    echo -e "\n${YELLOW}📦 Creando tabla ${table_name}...${NC}"
    
    # Intentar crear la tabla
    if eval "$create_cmd" 2>/dev/null; then
        echo -e "${GREEN}✅ Tabla ${table_name} creada exitosamente${NC}"
    else
        # Si falla, verificar si ya existe
        if aws dynamodb describe-table --table-name "$table_name" --endpoint-url http://localhost:8000 --no-cli-pager 2>/dev/null; then
            echo -e "${YELLOW}ℹ️  La tabla ${table_name} ya existe${NC}"
        else
            echo -e "${RED}❌ Error creando tabla ${table_name}${NC}"
            return 1
        fi
    fi
}

# Crear tabla de conversaciones
create_table "kavak-ai-agent-conversations-dev" 'aws dynamodb create-table \
    --table-name kavak-ai-agent-conversations-dev \
    --attribute-definitions \
        AttributeName=conversationId,AttributeType=S \
        AttributeName=messageId,AttributeType=S \
        AttributeName=userId,AttributeType=S \
    --key-schema \
        AttributeName=conversationId,KeyType=HASH \
        AttributeName=messageId,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --global-secondary-indexes "[
        {
            \"IndexName\": \"SummaryIndex\",
            \"KeySchema\": [{\"AttributeName\":\"conversationId\",\"KeyType\":\"HASH\"}],
            \"Projection\": {\"ProjectionType\":\"ALL\"}
        },
        {
            \"IndexName\": \"UserIdIndex\",
            \"KeySchema\": [{\"AttributeName\":\"userId\",\"KeyType\":\"HASH\"}],
            \"Projection\": {\"ProjectionType\":\"ALL\"}
        }
    ]" \
    --endpoint-url http://localhost:8000'

# Crear tabla de catálogo
create_table "kavak-ai-agent-catalog-dev" 'aws dynamodb create-table \
    --table-name kavak-ai-agent-catalog-dev \
    --attribute-definitions \
        AttributeName=stockId,AttributeType=S \
        AttributeName=make,AttributeType=S \
        AttributeName=model,AttributeType=S \
        AttributeName=price,AttributeType=N \
        AttributeName=year,AttributeType=N \
    --key-schema \
        AttributeName=stockId,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --global-secondary-indexes "[
        {
            \"IndexName\": \"MakeModelIndex\",
            \"KeySchema\": [
                {\"AttributeName\":\"make\",\"KeyType\":\"HASH\"},
                {\"AttributeName\":\"model\",\"KeyType\":\"RANGE\"}
            ],
            \"Projection\": {\"ProjectionType\":\"ALL\"}
        },
        {
            \"IndexName\": \"PriceYearIndex\",
            \"KeySchema\": [
                {\"AttributeName\":\"price\",\"KeyType\":\"HASH\"},
                {\"AttributeName\":\"year\",\"KeyType\":\"RANGE\"}
            ],
            \"Projection\": {\"ProjectionType\":\"ALL\"}
        }
    ]" \
    --endpoint-url http://localhost:8000'

# Crear tabla de embeddings
create_table "kavak-ai-agent-embeddings-dev" 'aws dynamodb create-table \
    --table-name kavak-ai-agent-embeddings-dev \
    --attribute-definitions \
        AttributeName=stockId,AttributeType=S \
        AttributeName=lastUpdate,AttributeType=S \
    --key-schema \
        AttributeName=stockId,KeyType=HASH \
        AttributeName=lastUpdate,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --global-secondary-indexes "[
        {
            \"IndexName\": \"LastUpdateIndex\",
            \"KeySchema\": [{\"AttributeName\":\"lastUpdate\",\"KeyType\":\"HASH\"}],
            \"Projection\": {\"ProjectionType\":\"ALL\"}
        }
    ]" \
    --endpoint-url http://localhost:8000'

# Crear tabla de prospectos
create_table "kavak-ai-agent-prospects-dev" 'aws dynamodb create-table \
    --table-name kavak-ai-agent-prospects-dev \
    --attribute-definitions \
        AttributeName=whatsappNumber,AttributeType=S \
        AttributeName=appointmentId,AttributeType=S \
        AttributeName=appointmentDate,AttributeType=S \
        AttributeName=status,AttributeType=S \
    --key-schema \
        AttributeName=whatsappNumber,KeyType=HASH \
        AttributeName=appointmentId,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --global-secondary-indexes "[
        {
            \"IndexName\": \"DateStatusIndex\",
            \"KeySchema\": [
                {\"AttributeName\":\"appointmentDate\",\"KeyType\":\"HASH\"},
                {\"AttributeName\":\"status\",\"KeyType\":\"RANGE\"}
            ],
            \"Projection\": {\"ProjectionType\":\"ALL\"}
        }
    ]" \
    --endpoint-url http://localhost:8000'

# Listar todas las tablas al final
echo -e "\n${YELLOW}📋 Tablas creadas en DynamoDB local:${NC}"
aws dynamodb list-tables --endpoint-url http://localhost:8000 --no-cli-pager | jq -r '.TableNames[]' | while read -r table; do
    echo -e "${GREEN}✅ ${table}${NC}"
done 