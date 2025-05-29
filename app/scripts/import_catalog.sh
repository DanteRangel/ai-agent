#!/bin/bash

CSV_FILE=$1
TABLE_NAME=$2

if [ -z "$CSV_FILE" ] || [ -z "$TABLE_NAME" ]; then
  echo "Uso: $0 archivo.csv nombre_tabla"
  exit 1
fi

# Convierte CSV a JSON
tmpfile=$(mktemp)
csvjson "$CSV_FILE" > "$tmpfile"

# Importa cada registro a DynamoDB
cat "$tmpfile" | jq -c '.[]' | while read -r item; do
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

  aws dynamodb put-item \
    --table-name "$TABLE_NAME" \
    --item "$transformed_item" \
    --region us-east-1

  echo "Importado: $(echo "$item" | jq -r '.stockId')"
done

rm "$tmpfile"
echo "Importación terminada." 