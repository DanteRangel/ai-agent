#!/bin/bash

# Colores para mensajes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar argumentos
if [ -z "$1" ]; then
    echo -e "${RED}❌ Error: Falta el archivo CSV${NC}"
    echo -e "Uso: $0 archivo.csv"
    exit 1
fi

CSV_FILE=$1
TABLE_NAME="kavak-ai-agent-catalog-dev"

# Verificar que el archivo existe
if [ ! -f "$CSV_FILE" ]; then
    echo -e "${RED}❌ Error: El archivo $CSV_FILE no existe${NC}"
    exit 1
fi

# Verificar que DynamoDB local está corriendo
echo -e "${YELLOW}🔍 Verificando DynamoDB local...${NC}"
if ! curl -s http://localhost:8000 > /dev/null; then
    echo -e "${RED}❌ DynamoDB local no está corriendo en http://localhost:8000${NC}"
    exit 1
fi

# Verificar que la tabla existe en local
echo -e "${YELLOW}🔍 Verificando tabla ${TABLE_NAME}...${NC}"
if ! aws dynamodb describe-table --table-name "$TABLE_NAME" --endpoint-url http://localhost:8000 --no-cli-pager > /dev/null 2>&1; then
    echo -e "${RED}❌ La tabla ${TABLE_NAME} no existe en DynamoDB local${NC}"
    echo -e "Por favor, crea las tablas primero con: ./scripts/create_local_tables.sh"
    exit 1
fi

# Verificar que no estamos conectados a AWS
if aws dynamodb list-tables --endpoint-url http://localhost:8000 --no-cli-pager 2>&1 | grep -q "kavak-ai-agent"; then
    echo -e "${YELLOW}⚠️  ADVERTENCIA: Parece que hay tablas de kavak-ai-agent en AWS${NC}"
    echo -e "Este script está diseñado para usar SOLO DynamoDB local"
    echo -e "Por favor, asegúrate de que tu configuración de AWS CLI no esté apuntando a AWS"
    echo -e "Puedes verificar tu configuración con: aws configure list"
    read -p "¿Deseas continuar de todos modos? (s/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        echo -e "${YELLOW}Operación cancelada${NC}"
        exit 1
    fi
fi

echo -e "\n${YELLOW}📥 Importando catálogo a DynamoDB local...${NC}"
echo -e "Tabla: ${GREEN}${TABLE_NAME}${NC}"
echo -e "Archivo: ${GREEN}${CSV_FILE}${NC}"
echo -e "Endpoint: ${GREEN}http://localhost:8000${NC}"

# Verificar que csvjson está instalado
if ! command -v csvjson &> /dev/null; then
    echo -e "${RED}❌ Error: csvjson no está instalado${NC}"
    echo -e "Por favor, instala csvkit:"
    echo -e "pip install csvkit"
    exit 1
fi

# Verificar que jq está instalado
if ! command -v jq &> /dev/null; then
    echo -e "${RED}❌ Error: jq no está instalado${NC}"
    echo -e "Por favor, instala jq:"
    echo -e "brew install jq"
    exit 1
fi

# Convierte CSV a JSON
echo -e "\n${YELLOW}🔄 Convirtiendo CSV a JSON...${NC}"
tmpfile=$(mktemp)
if ! csvjson "$CSV_FILE" > "$tmpfile"; then
    echo -e "${RED}❌ Error convirtiendo CSV a JSON${NC}"
    rm "$tmpfile"
    exit 1
fi

# Contar registros
total_records=$(jq 'length' "$tmpfile")
echo -e "${GREEN}✅ Se encontraron ${total_records} registros para importar${NC}"

# Importa cada registro a DynamoDB local
echo -e "\n${YELLOW}📤 Importando registros...${NC}"
current=0
errors=0

cat "$tmpfile" | jq -c '.[]' | while read -r item; do
    ((current++))
    
    # Transforma el item para asegurar los tipos de datos correctos
    transformed_item=$(echo "$item" | jq -c '
        def tostring_if_number:
            if type == "number" then tostring else . end;
        
        {
            "stockId": { "S": (.stockId|tostring_if_number) },
            "make": { "S": .make },
            "model": { "S": .model },
            "year": { "N": (.year|tostring_if_number) },
            "price": { "N": (.price|tostring_if_number) },
            "km": { "N": (.km|tostring_if_number) },
            "version": { "S": (.version // "") },
            "bluetooth": { "BOOL": (.bluetooth == "Sí") },
            "carPlay": { "BOOL": (.carPlay == "Sí") },
            "largo": { "N": (.largo|tostring_if_number) },
            "ancho": { "N": (.ancho|tostring_if_number) },
            "altura": { "N": (.altura|tostring_if_number) }
        } | with_entries(select(.value != null and .value != "" and .value != "null"))
    ')

    if aws dynamodb put-item \
        --endpoint-url http://localhost:8000 \
        --table-name "$TABLE_NAME" \
        --item "$transformed_item" \
        --region us-east-1 \
        --no-cli-pager 2>/dev/null; then
        echo -e "${GREEN}✅ [${current}/${total_records}] Importado: $(echo "$item" | jq -r '.stockId')${NC}"
    else
        echo -e "${RED}❌ [${current}/${total_records}] Error importando: $(echo "$item" | jq -r '.stockId')${NC}"
        ((errors++))
    fi
done

rm "$tmpfile"

# Mostrar resumen
echo -e "\n${YELLOW}✨ Resumen de la importación:${NC}"
echo -e "Total registros: ${GREEN}${total_records}${NC}"
echo -e "Errores: ${RED}${errors}${NC}"

if [ $errors -eq 0 ]; then
    echo -e "\n${GREEN}✅ Importación completada exitosamente${NC}"
else
    echo -e "\n${YELLOW}⚠️  Importación completada con ${errors} errores${NC}"
    exit 1
fi 